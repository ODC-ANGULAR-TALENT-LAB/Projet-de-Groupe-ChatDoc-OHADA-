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


def test_fournisseur_indisponible_reste_en_lexical_seul(sans_base, monkeypatch):
    """Le comportement d'origine, qui doit survivre au correctif."""
    def echouer(textes, simuler=False):
        raise RuntimeError("fournisseur d'embeddings injoignable")

    monkeypatch.setattr(recherche, "calculer_embeddings", echouer)
    monkeypatch.setattr(recherche, "rechercher_vectoriel", lambda cx, v, s: [])

    _, mode = recherche.rechercher_detaille("mentions du registre")

    assert mode == "lexical_seul"
