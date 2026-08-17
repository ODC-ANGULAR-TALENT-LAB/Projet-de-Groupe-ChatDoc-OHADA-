"""Tests de l'analyse de conformite.

Deux choses sont verifiees : que la grille vient bien du CORPUS, et que
le doute profite toujours au « a verifier ». La seconde est la plus
importante — annoncer conforme a tort donne a l'utilisateur une fausse
securite, ce qui est le pire resultat possible pour cet outil.
"""

from __future__ import annotations

import pytest

from app.services import conformite
from app.services.conformite import (
    DocumentRefuse,
    analyser,
    extraire_texte,
    mentions_obligatoires,
    resumer,
)

# Extrait reel de l'article 13 de l'AUSCGIE, tel qu'il figure en base.
ARTICLE_13 = (
    "Les statuts mentionnent : 1° la forme de la société ; 2° sa dénomination "
    "suivie, le cas échéant, de son sigle ; 3° la nature et le domaine de son "
    "activité, qui forment son objet social ; 4° son siège social ; 5° sa durée ; "
    "10° le montant du capital social ."
)


# ---------------------------------------------------------------------
# La grille vient du corpus
# ---------------------------------------------------------------------


def test_les_mentions_sont_extraites_de_l_article():
    """La liste n'est pas ecrite a la main : elle est LUE dans le texte.

    Quand une revision change la liste, la grille change avec elle. Une
    liste codee en dur se serait perimee au premier acte revise, sans
    que rien ne le signale.
    """
    points = mentions_obligatoires(ARTICLE_13)

    assert [p["repere"] for p in points] == ["1°", "2°", "3°", "4°", "5°", "10°"]
    assert points[0]["libelle"] == "la forme de la société"
    assert points[5]["libelle"] == "le montant du capital social"


def test_un_article_sans_enumeration_ne_produit_aucun_point():
    assert mentions_obligatoires("Toute societe a un siege social.") == []


# ---------------------------------------------------------------------
# Le doute profite au « a verifier »
# ---------------------------------------------------------------------


def points_essai() -> list[dict]:
    return [
        {"repere": "1°", "libelle": "la forme de la société"},
        {"repere": "2°", "libelle": "sa dénomination"},
    ]


def test_un_point_non_rendu_par_le_modele_revient_a_verifier(monkeypatch):
    """Une absence de reponse ne vaut pas une conformite.

    Si le modele oublie un point, le rapport doit le dire — pas le
    compter comme satisfait par defaut.
    """
    monkeypatch.setattr(
        conformite,
        "appeler_llm",
        lambda **_: {"points": [{"repere": "1°", "statut": "conforme", "constat": "Vu."}]},
    )

    rapport = analyser("un document", points_essai())

    assert rapport[0]["statut"] == "conforme"
    assert rapport[1]["statut"] == "a_verifier"
    assert len(rapport) == 2


def test_un_statut_inconnu_revient_a_verifier(monkeypatch):
    monkeypatch.setattr(
        conformite,
        "appeler_llm",
        lambda **_: {
            "points": [{"repere": "1°", "statut": "parfait", "constat": "?"}]
        },
    )

    assert analyser("un document", points_essai())[0]["statut"] == "a_verifier"


def test_une_panne_du_modele_ne_declare_rien_conforme(monkeypatch):
    """Le repli est « a verifier », jamais « conforme »."""
    monkeypatch.setattr(conformite, "appeler_llm", lambda **_: {"points": []})

    rapport = analyser("un document", points_essai())

    assert all(p["statut"] == "a_verifier" for p in rapport)


def test_l_ordre_de_la_grille_est_preserve(monkeypatch):
    """Le modele peut repondre dans le desordre ; le rapport, non.

    Le juriste relit une liste ordonnee comme celle de l'article.
    """
    monkeypatch.setattr(
        conformite,
        "appeler_llm",
        lambda **_: {
            "points": [
                {"repere": "2°", "statut": "ecart", "constat": "Absente."},
                {"repere": "1°", "statut": "conforme", "constat": "Presente."},
            ]
        },
    )

    rapport = analyser("un document", points_essai())

    assert [p["repere"] for p in rapport] == ["1°", "2°"]


# ---------------------------------------------------------------------
# Le document depose
# ---------------------------------------------------------------------


def test_un_format_non_pris_en_charge_est_refuse():
    with pytest.raises(DocumentRefuse, match="Format"):
        extraire_texte(b"contenu", "statuts.docx")


def test_un_document_trop_volumineux_est_refuse():
    enorme = b"x" * (conformite.TAILLE_MAXIMALE + 1)

    with pytest.raises(DocumentRefuse, match="volumineux"):
        extraire_texte(enorme, "statuts.pdf")


def test_aucun_indice_global_n_est_calcule():
    """Un pourcentage serait un mensonge commode.

    « 85 % conforme » se retient, se cite, et laisse croire a une
    garantie que le produit refuse explicitement de donner. On rend des
    comptes, pas une note.
    """
    compte = resumer(
        [
            {"statut": "conforme"},
            {"statut": "ecart"},
            {"statut": "a_verifier"},
            {"statut": "conforme"},
        ]
    )

    assert compte == {"conforme": 2, "ecart": 1, "a_verifier": 1}
    assert "indice" not in compte and "pourcentage" not in compte


# ---------------------------------------------------------------------
# Un renvoi n'est pas une mention
# ---------------------------------------------------------------------

# Debut reel de l'article 397 de l'AUSCGIE, tel qu'il figure en base.
ARTICLE_397 = (
    "Les statuts doivent contenir les énonciations prévues à l’article 13 "
    "ci-dessus, à l’exception du 6°) ci-après. Ils doivent indiquer en outre : "
    "1° le mode d’administration et de direction retenu ; "
    "2° selon le cas, soit les nom, prénoms, adresse."
)

# L'AUSCOOP ferme la parenthese du repere : « 1°) » et non « 1° ».
ARTICLE_18_COOP = (
    "Les statuts comportent obligatoirement : 1°) la forme de la société "
    "coopérative ; 2°) sa dénomination suivie, le cas échéant, de son sigle ; "
    "3°) son siège et sa durée."
)


def test_un_renvoi_n_est_pas_une_mention():
    """« à l'exception du 6°) ci-après » désigne un point qu'on EXCLUT.

    Le prendre pour une mention à vérifier produisait un point de
    contrôle absurde — « ) ci-après. Ils doivent indiquer en outre : » —
    envoyé tel quel au modèle.
    """
    points = mentions_obligatoires(ARTICLE_397)

    assert [p["repere"] for p in points] == ["1°", "2°"]
    assert points[0]["libelle"] == "le mode d’administration et de direction retenu"


def test_le_repere_avec_parenthese_est_reconnu():
    """L'AUSCOOP écrit « 1°) », l'AUSCGIE « 1° ». Les deux sont des listes."""
    points = mentions_obligatoires(ARTICLE_18_COOP)

    assert [p["repere"] for p in points] == ["1°", "2°", "3°"]
    assert points[0]["libelle"] == "la forme de la société coopérative"
    assert not points[0]["libelle"].startswith(")")


def test_le_libelle_ne_garde_ni_point_virgule_ni_point_final():
    points = mentions_obligatoires(ARTICLE_18_COOP)

    assert all(not p["libelle"].endswith((";", ".")) for p in points)


# ---------------------------------------------------------------------
# Une puce peut s'intercaler entre le séparateur et le repère
# ---------------------------------------------------------------------

# Début RÉEL de l'article 13 de l'AUSCGIE, copié depuis la base — puces
# comprises. Les extraits reconstitués plus haut dans ce fichier les
# avaient perdues, et c'est précisément ce qui a laissé passer le défaut.
ARTICLE_13_REEL = (
    "Les statuts mentionnent : • 1° la forme de la société ; • 2° sa "
    "dénomination suivie, le cas échéant, de son sigle ; • 3° la nature et "
    "le domaine de son activité, qui forment son objet social ; • 4° son "
    "siège social ; • 5° sa durée."
)

ARTICLE_397_REEL = (
    "Les statuts doivent contenir les énonciations prévues à l’article 13 "
    "ci-dessus, à l’exception du 6°) ci-après. Ils doivent indiquer en "
    "outre : • 1° le mode d’administration et de direction retenu ; • 2° "
    "selon le cas, soit les nom, prénoms, adresse."
)


def test_une_puce_entre_le_separateur_et_le_repere_est_toleree():
    """LE DÉFAUT QUE CE TEST EMPÊCHE DE REVENIR.

    L'édition de l'AUSCGIE compose ses énumérations avec une puce :
    « mentionnent : • 1° la forme ». Le motif exigeait que le chiffre
    suive immédiatement le deux-points, et rendait donc ZÉRO mention sur
    les articles 13 et 397 — les deux modèles les plus utilisés de
    l'analyse de conformité ET du générateur de documents.

    Rien ne le signalait : les tests travaillaient sur un extrait
    retapé à la main, sans puces.
    """
    points = mentions_obligatoires(ARTICLE_13_REEL)

    assert [p["repere"] for p in points] == ["1°", "2°", "3°", "4°", "5°"]
    assert points[0]["libelle"] == "la forme de la société"
    # La puce ne doit pas non plus se retrouver DANS le libellé.
    assert all("•" not in p["libelle"] for p in points)


def test_le_renvoi_reste_exclu_malgre_les_puces():
    """La tolérance ne doit pas rouvrir la porte au faux positif.

    « à l'exception du 6°) ci-après » désigne un point qu'on EXCLUT : il
    ne suit ni deux-points ni point-virgule, et doit le rester.
    """
    points = mentions_obligatoires(ARTICLE_397_REEL)

    assert [p["repere"] for p in points] == ["1°", "2°"]
    assert points[0]["libelle"] == "le mode d’administration et de direction retenu"
