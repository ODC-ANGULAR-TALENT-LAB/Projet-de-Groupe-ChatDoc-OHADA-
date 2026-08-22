"""Un corpus charge mais pas encore vectorise doit rester interrogeable.

CE QUE CES CAS PROTEGENT. La vectorisation est une etape HORS LIGNE,
posterieure au chargement : toute base fraichement remplie passe donc
par un moment ou elle contient des articles et aucun vecteur. C'est
l'etat normal d'une mise en service, pas une avarie.

Le defaut corrige ici etait retors. `pertinence()` ne lit que le score
vectoriel ; sans vecteurs en base, elle vaut 0 pour toute question. Le
seuil de refus etant a 0,55, l'assistant refusait TOUT — alors que la
recherche lexicale remontait des articles justes.

Et il ne se declarait qu'une fois le fournisseur d'embeddings
configure : tant qu'il manquait, l'appel echouait et le mode basculait
en "lexical_seul", qui neutralise le seuil. Renseigner une cle CASSAIT
donc le produit, ce qu'aucune intuition ne suggere.
"""

from contextlib import contextmanager

import pytest

from app.services import recherche

LEXICAUX = [
    {"id": 1, "numero": "12", "contenu": "...", "score_lexical": 0.91},
    {"id": 2, "numero": "13", "contenu": "...", "score_lexical": 0.44},
]

VECTORIELS = [
    {"id": 1, "numero": "12", "contenu": "...", "score_vectoriel": 0.78},
]


@pytest.fixture
def sans_base(monkeypatch):
    """Neutralise tout ce qui sortirait du processus.

    Les tests de ce projet ne dependent pas d'une base en marche : ce
    qui est verifie ici est une DECISION, et elle doit pouvoir l'etre
    sans PostgreSQL ni fournisseur d'embeddings.
    """

    @contextmanager
    def connexion_factice():
        yield None

    monkeypatch.setattr(recherche.moteur, "connect", connexion_factice)
    monkeypatch.setattr(
        recherche, "calculer_embeddings", lambda textes, simuler=False: [[0.1] * 4]
    )
    monkeypatch.setattr(
        recherche, "rechercher_lexical", lambda cx, q, sigle: list(LEXICAUX)
    )
    # Corpus entierement vectorise par defaut : c'est l'etat nominal, et
    # les cas qui testent une couverture partielle le redisent
    # explicitement. Sans cette valeur, la vraie fonction interrogerait
    # la base — que cette fixture a justement neutralisee.
    monkeypatch.setattr(recherche, "couverture_vectorielle", lambda: 1.0)


def test_corpus_sans_vecteurs_bascule_en_lexical_seul(sans_base, monkeypatch):
    """LE CORRECTIF. La question se vectorise, le corpus non.

    C'est exactement l'etat d'une base fraichement chargee dont la cle
    d'embeddings vient d'etre renseignee.
    """
    monkeypatch.setattr(recherche, "rechercher_vectoriel", lambda cx, v, s: [])

    resultats, mode = recherche.rechercher_detaille("mentions du registre")

    assert mode == "lexical_seul", (
        "sans le moindre vecteur en base, le seuil de pertinence n'a "
        "aucun signal a mesurer : le mode doit le dire"
    )
    assert resultats, "la recherche lexicale doit tout de meme repondre"
    assert recherche.pertinence(resultats) == 0.0


def test_corpus_vectorise_reste_en_hybride(sans_base, monkeypatch):
    """Le cas nominal ne doit pas etre emporte par le correctif.

    Des qu'un signal vectoriel existe, le mode reste "hybride" et le
    seuil retrouve son role — dont celui de refuser une question
    reellement hors corpus.
    """
    monkeypatch.setattr(
        recherche, "rechercher_vectoriel", lambda cx, v, s: list(VECTORIELS)
    )

    resultats, mode = recherche.rechercher_detaille("mentions du registre")

    assert mode == "hybride"
    assert recherche.pertinence(resultats) == pytest.approx(0.78)


def test_couverture_partielle_ignore_le_signal_vectoriel(sans_base, monkeypatch):
    """UNE VECTORISATION PARTIELLE EST PIRE QU'AUCUNE.

    Des qu'un article porte un vecteur, la moitie vectorielle remonte
    quelque chose — mais seulement parmi les articles deja vectorises.
    Pour une question portant sur un texte encore absent de ce
    sous-ensemble, `pertinence()` mesure donc la ressemblance des
    articles les moins mauvais du lot disponible, et non celle des
    articles justes, que seul le lexical a trouves.

    Sous le seuil, la question est alors REFUSEE alors que la recherche
    lexicale y repondait. Le cas n'a rien de theorique : il decrit tout
    corpus en cours de vectorisation, ce qui peut durer des jours quand
    le fournisseur limite la cadence.
    """
    monkeypatch.setattr(
        recherche, "rechercher_vectoriel", lambda cx, v, s: list(VECTORIELS)
    )
    monkeypatch.setattr(recherche, "couverture_vectorielle", lambda: 0.15)

    resultats, mode = recherche.rechercher_detaille("mentions du registre")

    assert mode == "lexical_seul"
    assert recherche.pertinence(resultats) == 0.0, (
        "le score vectoriel d'un corpus incomplet ne doit pas servir "
        "a decider d'un refus"
    )


def test_couverture_suffisante_retablit_l_hybride(sans_base, monkeypatch):
    """Le seuil ne doit pas exiger la perfection.

    Quelques articles non vectorises — un chargement recent, un texte
    ajoute la veille — ne doivent pas priver tout le produit de sa
    recherche semantique.
    """
    monkeypatch.setattr(
        recherche, "rechercher_vectoriel", lambda cx, v, s: list(VECTORIELS)
    )
    monkeypatch.setattr(recherche, "couverture_vectorielle", lambda: 0.97)

    _, mode = recherche.rechercher_detaille("mentions du registre")

    assert mode == "hybride"


def test_fournisseur_indisponible_reste_en_lexical_seul(sans_base, monkeypatch):
    """Le comportement d'origine, qui doit survivre au correctif."""
    def echouer(textes, simuler=False):
        raise RuntimeError("fournisseur d'embeddings injoignable")

    monkeypatch.setattr(recherche, "calculer_embeddings", echouer)
    monkeypatch.setattr(recherche, "rechercher_vectoriel", lambda cx, v, s: [])

    _, mode = recherche.rechercher_detaille("mentions du registre")

    assert mode == "lexical_seul"
