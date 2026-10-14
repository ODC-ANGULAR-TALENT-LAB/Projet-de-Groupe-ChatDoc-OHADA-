"""Ordre de vectorisation : le droit des societes et la fiscalite d'abord.

POURQUOI. Le quota gratuit d'embeddings ne couvre qu'environ 1 000
articles par jour, et la file suivait l'ordre d'insertion. AUSCGIE et le
CGI, charges en dernier, passaient donc apres tous les autres — alors
que ce sont les deux promesses du titre de la page d'accueil (« le droit
OHADA et la fiscalite camerounaise ») et le sujet des questions
d'exemple. Le 14 octobre 2026, avec 1 022 articles vectorises sur 5 563,
AUCUN des deux n'en avait : l'assistant refusait « Combien d'associes
minimum dans une SARL ? » et se trompait d'un facteur dix sur le capital
minimum d'une SA.

Test en lecture seule sur la base locale ; il est saute si elle est
injoignable.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from app.db import moteur
from app.services.vectorisation import TEXTES_PRIORITAIRES, articles_a_traiter


@pytest.fixture
def file_d_attente() -> list[dict]:
    try:
        with moteur.connect() as cx:
            return articles_a_traiter(cx)
    except OperationalError:
        pytest.skip("base locale injoignable")


def rang(sigle: str) -> int:
    return (
        TEXTES_PRIORITAIRES.index(sigle)
        if sigle in TEXTES_PRIORITAIRES
        else len(TEXTES_PRIORITAIRES)
    )


def test_les_textes_prioritaires_sont_auscgie_puis_cgi():
    assert TEXTES_PRIORITAIRES[:2] == ("AUSCGIE", "CGI")


def test_la_file_traite_les_textes_prioritaires_en_premier(file_d_attente):
    rangs = [rang(article["sigle"]) for article in file_d_attente]

    # Jamais un article d'un texte moins prioritaire avant un plus
    # prioritaire : la suite des rangs ne redescend pas.
    assert rangs == sorted(rangs)


def test_la_file_commence_par_un_texte_prioritaire_quand_il_en_reste(
    file_d_attente,
):
    prioritaires_restants = [
        a for a in file_d_attente if a["sigle"] in TEXTES_PRIORITAIRES
    ]
    if not prioritaires_restants:
        pytest.skip("textes prioritaires deja vectorises")

    assert file_d_attente[0]["sigle"] in TEXTES_PRIORITAIRES
