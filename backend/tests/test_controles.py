"""Tests des controles automatiques du corpus (B.4) et de
l'echantillonnage de relecture (B.5).

Ces controles sont la barriere avant le chargement en base. Un controle
qui laisse passer un defaut est pire que pas de controle du tout : il
donne une fausse assurance sur un corpus qui a seulement l'air fiable.
"""

from __future__ import annotations

import pytest

CHEMIN = "Livre I - Dispositions generales > Titre II - Des societes"
CORPS = "Le capital social est divise en parts sociales egales. " * 3


def article(numero: str, contenu: str = CORPS, chemin: str = CHEMIN, page: int = 2):
    return {
        "numero": numero,
        "chemin": chemin,
        "contenu": contenu,
        "page_debut": page,
    }


@pytest.fixture
def corpus_sain():
    """Vingt articles consecutifs, plus un article "18 bis"."""
    articles = [article(str(n), page=2 + n // 5) for n in range(1, 21)]
    articles.insert(18, article("18 bis", page=5))
    return articles


def messages_bloquants(controleur, articles) -> list[str]:
    return [
        message
        for niveau, message in controleur.controler(articles)
        if niveau == controleur.BLOQUANT
    ]


def test_corpus_sain_ne_remonte_aucun_bloquant(controleur, corpus_sain):
    assert messages_bloquants(controleur, corpus_sain) == []


def test_article_bis_ne_compte_pas_comme_un_trou(controleur, corpus_sain):
    """"18 bis" partage sa partie entiere avec l'article 18 : il ne doit
    creer ni doublon ni trou dans la numerotation."""
    assert not any(
        "manquants" in message for message in messages_bloquants(controleur, corpus_sain)
    )


def test_doublon_detecte(controleur, corpus_sain):
    corpus_sain.append(article("7"))
    assert any(
        "double" in message for message in messages_bloquants(controleur, corpus_sain)
    )


def test_trou_detecte(controleur, corpus_sain):
    del corpus_sain[11]  # retire l'article 12
    assert any(
        "manquants" in message
        for message in messages_bloquants(controleur, corpus_sain)
    )


def test_article_trop_court_detecte(controleur, corpus_sain):
    corpus_sain[4] = article("5", contenu="Trop court.")
    assert any(
        "trop court" in message
        for message in messages_bloquants(controleur, corpus_sain)
    )


def test_article_abroge_ne_bloque_pas(controleur, corpus_sain):
    """Un article abroge est court par nature, et doit entrer au corpus.

    L'AUDCIF ecrit « Article 12 — Abroge ». Le refuser au chargement
    effacerait du corpus une information juridique de premier ordre : le
    juriste qui cherche cet article doit apprendre qu'il est abroge,
    pas ne rien trouver.
    """
    corpus_sain[4] = article("5", contenu="Abrogé")
    bloquants = messages_bloquants(controleur, corpus_sain)

    assert not any("trop court" in message for message in bloquants)
    # Mais la mention reste signalee au relecteur.
    tous = [message for _, message in controleur.controler(corpus_sain)]
    assert any("abroge" in message.lower() for message in tous)


def test_article_court_sans_mention_reste_bloquant(controleur, corpus_sain):
    """Le garde-fou : la tolerance ne vaut QUE pour une abrogation."""
    corpus_sain[4] = article("5", contenu="Voir ci-dessus.")
    assert any(
        "trop court" in message
        for message in messages_bloquants(controleur, corpus_sain)
    )


def test_article_trop_long_detecte(controleur, corpus_sain):
    """Le defaut le plus sournois : deux articles colles parce que
    l'expression reguliere n'a pas reconnu le second en-tete."""
    corpus_sain[9] = article("10", contenu="x" * 13000)
    assert any(
        "trop long" in message
        for message in messages_bloquants(controleur, corpus_sain)
    )


def test_chemin_absent_detecte(controleur, corpus_sain):
    corpus_sain[14] = article("15", chemin="")
    assert any(
        "sans chemin" in message
        for message in messages_bloquants(controleur, corpus_sain)
    )


def test_numero_illisible_detecte(controleur, corpus_sain):
    corpus_sain.append(article("premier"))
    assert any(
        "illisibles" in message
        for message in messages_bloquants(controleur, corpus_sain)
    )


def test_numero_entier_extrait_la_partie_numerique(controleur):
    assert controleur.numero_entier("18 bis") == 18
    assert controleur.numero_entier("92") == 92
    assert controleur.numero_entier("premier") is None


def test_echantillon_retient_le_premier_et_le_dernier(controleur, corpus_sain):
    """Ce sont eux qui revelent les debuts et fins de decoupage rates."""
    retenus = controleur.echantillonner(corpus_sain, 5, graine=1)
    assert retenus[0] is corpus_sain[0]
    assert retenus[-1] is corpus_sain[-1]
    assert len(retenus) == 5


def test_echantillon_reproductible(controleur, corpus_sain):
    """A graine egale, meme echantillon : la relecture doit pouvoir se
    reprendre a l'identique d'un jour a l'autre."""
    premier = controleur.echantillonner(corpus_sain, 6, graine=7)
    second = controleur.echantillonner(corpus_sain, 6, graine=7)
    assert [a["numero"] for a in premier] == [a["numero"] for a in second]


def test_echantillon_plus_grand_que_le_corpus(controleur, corpus_sain):
    retenus = controleur.echantillonner(corpus_sain, 999, graine=1)
    assert len(retenus) == len(corpus_sain)
