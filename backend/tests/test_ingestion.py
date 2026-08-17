"""Tests de l'ingestion d'un PDF téléversé (back-office).

Ce que ces tests protègent : rien n'entre dans le corpus sans être
passé par l'extraction, le découpage ET les contrôles. Un document
refusé ici est un document qui n'aurait jamais dû devenir citable.
"""

from __future__ import annotations

import pytest

from app.services.controles import BLOQUANT, bloquants, controler
from app.services.decoupage import decouper_texte
from app.services.ingestion import DepotRefuse, assembler_texte, ingerer

TEXTE_PAGINE = (
    "\n===PAGE 1===\nSOMMAIRE\nArticle 1 .......... 2\n"
    "\n===PAGE 2===\n"
    "LIVRE I : DISPOSITIONS GENERALES\n"
    "TITRE I - Du champ d'application\n"
    "Article 1\n"
    "La presente loi regit les societes commerciales et le groupement "
    "d'interet economique situe sur le territoire d'un Etat partie.\n"
    "Article 2\n"
    "Toute societe commerciale doit etre immatriculee au registre du "
    "commerce et du credit mobilier dans le mois de sa constitution.\n"
)


# ---------------------------------------------------------------------
# Refus au dépôt
# ---------------------------------------------------------------------


def test_fichier_vide_refuse():
    with pytest.raises(DepotRefuse, match="vide"):
        ingerer(b"")


def test_fichier_non_pdf_refuse():
    """L'en-tête %PDF est vérifié avant toute tentative de lecture :
    inutile de faire travailler pdfplumber sur un fichier arbitraire."""
    with pytest.raises(DepotRefuse, match="pas un PDF"):
        ingerer(b"MZ\x90\x00 un executable deguise en pdf")


def test_fichier_trop_volumineux_refuse():
    enorme = b"%PDF-1.4" + b"\x00" * (61 * 1024 * 1024)

    with pytest.raises(DepotRefuse, match="volumineux"):
        ingerer(enorme)


def test_pdf_illisible_refuse():
    """Un fichier qui commence par %PDF mais n'en est pas un doit
    produire un message exploitable, pas une trace de pile."""
    with pytest.raises(DepotRefuse, match="n'a pas pu etre lu"):
        ingerer(b"%PDF-1.4 puis n'importe quoi qui ne suit pas la specification")


# ---------------------------------------------------------------------
# Assemblage et découpage
# ---------------------------------------------------------------------


def test_assemblage_pose_les_marqueurs_de_page():
    texte = assembler_texte([(1, "premiere"), (2, "seconde")])

    assert "===PAGE 1===" in texte
    assert "===PAGE 2===" in texte
    assert texte.index("===PAGE 1===") < texte.index("===PAGE 2===")


def test_le_sommaire_est_ecarte_meme_sans_page_debut():
    """Le back-office ne connait pas la pagination du PDF depose.

    L'administrateur televerse un document sans indiquer ou commence le
    corps du texte : le sommaire doit donc etre reconnu a sa forme
    (points de conduite), pas seulement ecarte par une plage de pages.
    Les deux chemins doivent donner le meme resultat.
    """
    tous = decouper_texte(TEXTE_PAGINE)
    corps = decouper_texte(TEXTE_PAGINE, page_debut=2)

    assert [a["numero"] for a in tous] == ["1", "2"]
    assert [a["numero"] for a in corps] == ["1", "2"]


def test_le_chemin_hierarchique_est_reconstitue():
    articles = decouper_texte(TEXTE_PAGINE, page_debut=2)

    assert articles[0]["chemin"] == (
        "Livre I - DISPOSITIONS GENERALES > Titre I - Du champ d'application"
    )


# ---------------------------------------------------------------------
# Contrôles — la barrière avant validation
# ---------------------------------------------------------------------


def test_un_decoupage_propre_ne_bloque_pas():
    articles = decouper_texte(TEXTE_PAGINE, page_debut=2)

    assert bloquants(controler(articles)) == []


def test_article_trop_court_bloque():
    """Presque toujours un fragment de sommaire ou un en-tête isolé."""
    articles = [{"numero": "1", "chemin": "Livre I", "contenu": "Court."}]

    assert any("trop court" in m for m in bloquants(controler(articles)))


def test_article_trop_long_bloque():
    """Le défaut le plus sournois : deux articles fusionnés parce que
    l'expression régulière n'a pas reconnu le second en-tête."""
    articles = [{"numero": "1", "chemin": "Livre I", "contenu": "x" * 13000}]

    assert any("trop long" in m for m in bloquants(controler(articles)))


def test_trou_de_numerotation_bloque():
    articles = [
        {"numero": n, "chemin": "Livre I", "contenu": "Un contenu suffisamment long."}
        for n in ("1", "2", "5")
    ]

    assert any("manquants" in m for m in bloquants(controler(articles)))


def test_chemin_absent_bloque():
    """Un article sans chemin perd son contexte : il devient
    incompréhensible une fois vectorisé, et la recherche s'en ressent."""
    articles = [
        {"numero": "1", "chemin": "", "contenu": "Un contenu suffisamment long."}
    ]

    assert any("sans chemin" in m for m in bloquants(controler(articles)))


def test_les_avertissements_ne_bloquent_pas():
    """Profondeurs hiérarchiques variables : ça mérite un œil, pas un
    refus."""
    corps = "Un contenu de longueur suffisante pour passer le controle."
    articles = [
        {"numero": "1", "chemin": "Livre I", "contenu": corps},
        {"numero": "2", "chemin": "Livre I > Titre II", "contenu": corps},
        {
            "numero": "3",
            "chemin": "Livre I > Titre II > Chapitre 3",
            "contenu": corps,
        },
        {
            "numero": "4",
            "chemin": "Livre I > Titre II > Chapitre 3 > Section 1",
            "contenu": corps,
        },
    ]

    problemes = controler(articles)

    assert any(niveau != BLOQUANT for niveau, _ in problemes)
    assert bloquants(problemes) == []
