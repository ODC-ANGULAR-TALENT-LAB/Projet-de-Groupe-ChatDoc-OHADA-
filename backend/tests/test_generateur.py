"""Tests du générateur de documents types.

CE QUI EST VÉRIFIÉ ICI n'est pas la mise en page — un PDF mal aligné se
voit. Ce sont les deux propriétés dont dépend la valeur de l'outil :

1. Le questionnaire vient du CORPUS, pas d'une liste écrite à la main.
   C'est la même fonction que l'analyse de conformité : le document
   produit est donc, par construction, celui que l'analyse validerait.

2. Une mention sans réponse n'est jamais omise. Une clause absente
   passerait inaperçue à la relecture ; un trou visible saute aux yeux.
"""

from __future__ import annotations

import pytest

from app.services.conformite import mentions_obligatoires
from app.services.generateur import (
    MODELES,
    assembler,
    en_docx,
    en_pdf,
    questionnaire,
)

# Extrait réel de l'article 13 de l'AUSCGIE, tel qu'il figure en base.
ARTICLE_13 = (
    "Les statuts mentionnent : 1° la forme de la société ; 2° sa dénomination "
    "suivie, le cas échéant, de son sigle ; 3° la nature et le domaine de son "
    "activité, qui forment son objet social ; 4° son siège social ; 5° sa durée."
)


# ---------------------------------------------------------------------
# Le questionnaire vient du corpus
# ---------------------------------------------------------------------


def test_une_question_par_mention_obligatoire():
    champs = questionnaire(ARTICLE_13)

    assert [c["repere"] for c in champs] == ["1°", "2°", "3°", "4°", "5°"]


def test_le_questionnaire_suit_exactement_l_analyse_de_conformite():
    """LA PROPRIÉTÉ CENTRALE DE CE FICHIER.

    Générateur et analyse de conformité lisent la MÊME fonction. Deux
    listes tenues séparément auraient fini par diverger — et l'outil
    aurait généré des documents que son propre contrôle rejetait.
    """
    champs = questionnaire(ARTICLE_13)
    points = mentions_obligatoires(ARTICLE_13)

    assert [c["repere"] for c in champs] == [p["repere"] for p in points]
    assert [c["libelle_legal"] for c in champs] == [p["libelle"] for p in points]


def test_le_libelle_legal_n_est_pas_reecrit():
    """Réécrire un intitulé change ce que la loi demande.

    Le libellé sert aussi de point de comparaison mot pour mot avec le
    texte de l'article pendant la relecture.
    """
    champs = questionnaire(ARTICLE_13)

    assert champs[2]["libelle_legal"] == (
        "la nature et le domaine de son activité, qui forment son objet social"
    )
    # Seule la majuscule initiale change.
    assert champs[2]["question"].startswith("La nature et le domaine")


def test_un_article_sans_enumeration_ne_produit_aucune_question():
    assert questionnaire("Toute société a un siège social.") == []


# ---------------------------------------------------------------------
# L'assemblage
# ---------------------------------------------------------------------


def document_essai(reponses: dict[str, str]):
    return assembler(
        MODELES["statuts_sarl"],
        questionnaire(ARTICLE_13),
        reponses,
        "revision du 30 janvier 2014",
    )


def test_chaque_reponse_devient_une_clause():
    document = document_essai(
        {
            "mention_1": "Société à responsabilité limitée",
            "mention_2": "MBARGA & FILS SARL",
            "mention_3": "Négoce de matériaux",
            "mention_4": "Douala, Akwa",
            "mention_5": "99 ans",
        }
    )

    assert len(document["clauses"]) == 5
    assert document["clauses"][1]["contenu"] == "MBARGA & FILS SARL"
    assert document["restant_a_completer"] == 0


def test_une_mention_sans_reponse_laisse_un_trou_visible():
    """ELLE N'EST PAS OMISE, ET C'EST LE POINT.

    Une clause absente passerait inaperçue à la relecture ; un
    « [À COMPLÉTER] » saute aux yeux. Même principe que « le doute
    profite au à vérifier » de l'analyse de conformité.
    """
    document = document_essai({"mention_1": "SARL"})

    assert len(document["clauses"]) == 5
    assert document["restant_a_completer"] == 4
    manquante = document["clauses"][1]
    assert manquante["contenu"] == "[À COMPLÉTER]"
    assert manquante["complete"] is False


def test_une_reponse_vide_compte_comme_absente():
    document = document_essai({"mention_1": "   "})

    assert document["clauses"][0]["contenu"] == "[À COMPLÉTER]"


def test_l_avertissement_accompagne_le_document():
    """Le document circule détaché de l'application.

    Un squelette pris pour un acte prêt à signer est le scénario que ce
    produit existe pour écarter.
    """
    document = document_essai({})

    assert "SQUELETTE" in document["avertissement"]
    assert "avant toute signature" in document["avertissement"]


def test_la_base_legale_et_la_version_du_corpus_figurent_au_document():
    document = document_essai({})

    assert document["base_legale"] == "AUSCGIE — article 13"
    assert document["version_corpus"] == "revision du 30 janvier 2014"


# ---------------------------------------------------------------------
# Les deux exports
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "rendu,signature",
    [(en_docx, b"PK"), (en_pdf, b"%PDF-")],
)
def test_les_deux_formats_sont_produits(rendu, signature):
    """Le .docx se retouche, le PDF se transmet.

    Ne livrer que le PDF obligerait à retaper le document, ce qui vide
    le générateur de son intérêt.
    """
    octets = rendu(document_essai({"mention_1": "SARL"}))

    assert octets.startswith(signature)
    assert len(octets) > 1000


def test_le_pdf_neutralise_le_balisage_du_corpus():
    """« & » et « < » viennent du corpus comme des réponses saisies.

    ReportLab les interprète comme du balisage : sans neutralisation, un
    nom de société contenant « & » casse le rendu du document.
    """
    octets = en_pdf(document_essai({"mention_2": "MBARGA & FILS <SARL>"}))

    assert octets.startswith(b"%PDF-")
