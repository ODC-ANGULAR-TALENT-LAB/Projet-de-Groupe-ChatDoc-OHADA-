"""Tests de l'export PDF d'une reponse sourcee.

Un PDF circule DETACHE de l'interface qui le portait : il finit dans un
dossier client, une note de travail, parfois une piece transmise a un
tiers. Ce que le cahier des charges (§16 ter) impose d'y faire figurer
n'est donc pas decoratif, et ces tests le verifient.
"""

from __future__ import annotations

import datetime

import pdfplumber
import pytest

from app.services.export_pdf import AVERTISSEMENT, construire

CITATIONS = [
    {
        "sigle": "AUSCGIE",
        "numero": "853-5",
        "chemin": "Livre 4-2 - De la societe par actions simplifiee",
        "extrait": "Le montant du capital social est librement fixe par les statuts.",
    }
]


@pytest.fixture
def texte_du_pdf() -> str:
    octets = construire(
        question="Quel capital social minimum pour une SAS ?",
        reponse="Aucun capital minimum n'est exige.\nLe montant est libre.",
        citations=CITATIONS,
        versions_corpus=["AUSCGIE (revision 2014, consolide au 05/05/2014)"],
        genere_le=datetime.date(2026, 8, 15),
    )
    with pdfplumber.open(__import__("io").BytesIO(octets)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_le_pdf_est_un_pdf():
    octets = construire("Une question ?", "Une reponse.", [], [])

    assert octets.startswith(b"%PDF")


def test_la_question_et_la_reponse_figurent(texte_du_pdf):
    assert "capital social minimum pour une SAS" in texte_du_pdf
    assert "Aucun capital minimum" in texte_du_pdf


def test_l_extrait_officiel_figure_en_entier(texte_du_pdf):
    """C'est la piece justificative.

    Un export qui ne porterait que la synthese perdrait exactement ce
    qui fait la valeur du produit.
    """
    assert "librement fixe par les statuts" in texte_du_pdf
    assert "Article 853-5" in texte_du_pdf


def test_l_avertissement_suit_le_document(texte_du_pdf):
    """« Rappel repris dans chaque export PDF » (§16 ter).

    Sans lui, un lecteur qui recoit le PDF hors de l'application peut
    prendre une aide documentaire pour un avis juridique.
    """
    assert "aide a la recherche documentaire" in texte_du_pdf.lower()
    assert "ne constitue ni une consultation juridique" in texte_du_pdf.lower()


def test_la_version_du_corpus_est_imprimee(texte_du_pdf):
    """Une reponse exacte aujourd'hui sera fausse apres la prochaine loi
    de finances : le lecteur doit pouvoir dater ce qu'il lit."""
    assert "revision 2014" in texte_du_pdf
    assert "15/08/2026" in texte_du_pdf


def test_un_balisage_dans_le_corpus_ne_casse_pas_le_rendu():
    """ReportLab interprete un balisage : le contenu doit etre neutralise.

    Un article contenant « < » n'est pas une hypothese d'ecole — les
    textes fiscaux comparent des seuils.
    """
    octets = construire(
        question="Quel seuil ?",
        reponse="Le seuil est de <10 millions & plus.",
        citations=[
            {
                "sigle": "CGI",
                "numero": "92",
                "chemin": "",
                "extrait": "Chiffre d'affaires < 10 000 000 F & superieur a 0.",
            }
        ],
        versions_corpus=[],
    )

    assert octets.startswith(b"%PDF")


def test_sans_citation_le_pdf_reste_valide():
    """Un refus s'exporte aussi : il n'a simplement pas de base legale."""
    octets = construire(
        question="Une question hors corpus ?",
        reponse="Cette question depasse les textes disponibles.",
        citations=[],
        versions_corpus=[],
    )

    assert octets.startswith(b"%PDF")
    assert AVERTISSEMENT
