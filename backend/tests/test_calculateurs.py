"""Tests des calculateurs fiscaux.

CE QUI EST VÉRIFIÉ ICI n'est pas d'abord l'arithmétique — multiplier une
base par un taux ne se casse pas. C'est le **garde-fou** : un barème qui
ne correspond plus à l'article qui le fonde doit BLOQUER le calcul, pas
le fausser en silence.

Un taux périmé qui continue de s'afficher avec assurance est le pire
défaut possible pour cet outil : personne ne vérifie un chiffre qui a
l'air normal.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.calculateurs import (
    CalculRefuse,
    Parametre,
    arrondir,
    montant_valide,
    taux,
    verifier,
)


# ---------------------------------------------------------------------
# Reconnaissance d'un taux dans la prose d'un article
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "declare,texte",
    [
        ("19,25", "Le taux normal de la taxe est fixé à 19,25 %."),
        ("19,25", "Le taux est fixé à 19.25% du montant."),
        ("19,25", "Le taux est fixé à 19,25 pour cent."),
        ("33", "L'impôt est calculé au taux de 33 %."),
        ("33", "L'impôt est calculé au taux de 33%."),
    ],
)
def test_un_taux_present_dans_l_article_est_reconnu(declare, texte):
    assert taux("t", "Taux", declare, "1").motif.search(texte)


@pytest.mark.parametrize(
    "declare,texte,pourquoi",
    [
        ("19,25", "Le taux est de 119,25 %.", "sous-chaîne à gauche"),
        ("19,25", "Un montant de 2 019,25 %.", "chiffre collé à gauche"),
        ("33", "Le taux est de 33,5 %.", "décimale à droite"),
        ("33", "Le taux est de 133 %.", "sous-chaîne à gauche"),
        ("2", "Une taxe de 12 %.", "sous-chaîne à gauche"),
        ("2", "Une taxe de 2,5 %.", "décimale à droite"),
        ("19,25", "Le taux est de 19 %.", "valeur différente"),
    ],
)
def test_un_taux_absent_n_est_pas_reconnu(declare, texte, pourquoi):
    """Les deux frontières du motif ne sont pas décoratives.

    Sans elles, le garde-fou validerait un taux que l'article ne porte
    pas — c'est-à-dire exactement ce qu'il est censé empêcher.
    """
    assert not taux("t", "Taux", declare, "1").motif.search(texte), pourquoi


# ---------------------------------------------------------------------
# Le garde-fou : le corpus a le dernier mot
# ---------------------------------------------------------------------


class SessionFactice:
    """Session minimale rendant un article, ou rien.

    Ces tests ne touchent pas la base : ce qu'on vérifie est la
    DÉCISION prise face à un article, pas la requête SQL.
    """

    def __init__(self, article: dict | None):
        self._article = article

    def execute(self, *_args, **_kwargs):
        return self

    def mappings(self):
        return self

    def first(self):
        return self._article


def article(contenu: str, numero: str = "128") -> dict:
    return {"numero": numero, "chemin": "Livre I > Titre II", "contenu": contenu}


TVA = taux("normal", "Taux normal de TVA", "19,25", "128")


def test_un_taux_confirme_par_l_article_donne_la_base_legale():
    session = SessionFactice(
        article("Le taux général de la taxe sur la valeur ajoutée est de 19,25 %.")
    )

    base = verifier(session, TVA)

    assert base["valeur"] == "19.25"
    assert base["sigle"] == "CGI"
    assert base["numero"] == "128"
    # L'extrait officiel accompagne le résultat : c'est ce qui permet au
    # professionnel de justifier son calcul.
    assert "19,25 %" in base["extrait"]
    assert base["chemin"] == "Livre I > Titre II"


def test_un_bareme_perime_bloque_le_calcul():
    """LE TEST CENTRAL DE CE FICHIER.

    Une loi de finances porte le taux à 20 % ; le corpus est mis à jour,
    la déclaration ne l'est pas. Le calcul doit s'arrêter — pas
    continuer avec l'ancien taux.
    """
    session = SessionFactice(
        article("Le taux général de la taxe sur la valeur ajoutée est de 20 %.")
    )

    with pytest.raises(CalculRefuse, match="barème"):
        verifier(session, TVA)


def test_un_article_absent_du_corpus_bloque_le_calcul():
    """Sans base légale vérifiable, pas de chiffre.

    Rendre un résultat en signalant seulement « article introuvable »
    reviendrait à livrer le chiffre quand même : il serait lu, retenu,
    et cité.
    """
    with pytest.raises(CalculRefuse, match="absent du corpus"):
        verifier(SessionFactice(None), TVA)


def test_le_motif_de_refus_nomme_l_article():
    """Un refus doit être actionnable par le juriste qui le reçoit."""
    with pytest.raises(CalculRefuse, match=r"128"):
        verifier(SessionFactice(None), TVA)


# ---------------------------------------------------------------------
# Saisie de l'utilisateur
# ---------------------------------------------------------------------


@pytest.mark.parametrize("brut,attendu", [("1000", 1000), (0, 0), ("15000000.50", None)])
def test_un_montant_correct_est_accepte(brut, attendu):
    montant = montant_valide(brut)
    if attendu is not None:
        assert montant == Decimal(attendu)


@pytest.mark.parametrize("brut", ["-1", -0.01, "abc", "", None, "1e20"])
def test_une_saisie_absurde_est_refusee_plutot_que_calculee(brut):
    """Une erreur de saisie renvoyée à l'utilisateur, pas un résultat.

    Un chiffre produit à partir d'une saisie absurde ressemble à un
    résultat, et se cite comme tel.
    """
    with pytest.raises(CalculRefuse):
        montant_valide(brut)


def test_l_arrondi_se_fait_au_franc():
    """Le franc CFA n'a pas de subdivision en usage."""
    assert arrondir(Decimal("2887500.4")) == Decimal("2887500")
    assert arrondir(Decimal("2887500.5")) == Decimal("2887501")


def test_un_parametre_est_immuable():
    """Un barème modifié en cours d'exécution serait intraçable."""
    with pytest.raises(Exception):
        TVA.valeur = Decimal("20")  # type: ignore[misc]


def test_la_declaration_porte_la_valeur_attendue():
    assert isinstance(TVA, Parametre)
    assert TVA.valeur == Decimal("19.25")
    assert TVA.numero_article == "128"


# ---------------------------------------------------------------------
# La liquidation elle-même
# ---------------------------------------------------------------------

ARTICLE_TVA = article(
    "Le taux général de la taxe sur la valeur ajoutée est fixé à 19,25 %."
)


def test_la_tva_sur_un_montant_hors_taxes():
    from app.services.calculateurs import calculer_tva

    resultat = calculer_tva(SessionFactice(ARTICLE_TVA), "10000", False, TVA)

    montants = {ligne["libelle"]: ligne["montant"] for ligne in resultat["lignes"]}
    assert montants["Base imposable (HT)"] == "10000"
    assert resultat["resultat"]["montant"] == "1925"
    assert montants["Montant toutes taxes comprises (TTC)"] == "11925"


def test_la_tva_extraite_d_un_montant_ttc():
    """LE PIÈGE CLASSIQUE, et la raison d'être des deux sens de calcul.

    Retrancher naïvement 19,25 % d'un TTC de 11 925 donnerait 9 629 —
    et non 10 000. Le comptable qui ventile une dépense déjà réglée part
    du TTC : lui servir la soustraction naïve fausserait sa déclaration.
    """
    from app.services.calculateurs import calculer_tva

    resultat = calculer_tva(SessionFactice(ARTICLE_TVA), "11925", True, TVA)

    montants = {ligne["libelle"]: ligne["montant"] for ligne in resultat["lignes"]}
    assert montants["Base imposable (HT)"] == "10000"
    assert resultat["resultat"]["montant"] == "1925"


def test_chaque_ligne_de_taux_porte_sa_base_legale():
    """Sans l'article, le résultat n'est qu'un chiffre.

    C'est la user story du cahier des charges : « justifier le calcul ».
    """
    from app.services.calculateurs import calculer_tva

    resultat = calculer_tva(SessionFactice(ARTICLE_TVA), "10000", False, TVA)

    ligne_taxe = next(l for l in resultat["lignes"] if "base_legale" in l)
    assert ligne_taxe["base_legale"]["numero"] == "128"
    assert "19,25 %" in ligne_taxe["base_legale"]["extrait"]

    # La base saisie par l'utilisateur ne se fonde sur AUCUN article :
    # lui en attacher un fabriquerait une référence.
    base = next(l for l in resultat["lignes"] if l["libelle"].startswith("Base"))
    assert "base_legale" not in base


def test_un_impot_proportionnel_applique_son_taux():
    from app.services.calculateurs import calculer_impot_proportionnel

    parametre = taux("is", "Taux de l'impôt sur les sociétés", "33", "17")
    session = SessionFactice(
        article("L'impôt sur les sociétés est calculé au taux de 33 %.", numero="17")
    )

    resultat = calculer_impot_proportionnel(
        session, "1000000", parametre, "Impôt sur les sociétés", "Résultat fiscal"
    )

    assert resultat["resultat"]["montant"] == "330000"
    assert resultat["lignes"][1]["base_legale"]["numero"] == "17"


def test_un_calcul_dont_le_bareme_est_perime_ne_rend_aucun_chiffre():
    """Le refus doit interrompre le calcul, pas l'accompagner."""
    from app.services.calculateurs import calculer_tva

    session = SessionFactice(article("Le taux général est désormais fixé à 20 %."))

    with pytest.raises(CalculRefuse):
        calculer_tva(session, "10000", False, TVA)
