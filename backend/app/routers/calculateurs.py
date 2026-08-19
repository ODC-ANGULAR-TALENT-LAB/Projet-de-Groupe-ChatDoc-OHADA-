"""Calculateurs fiscaux relies aux articles du Code general des impots.

CE QUE CES ROUTES RENDENT : un resultat detaille, dont chaque ligne
portant un taux cite l'article qui le fonde et reproduit son extrait
officiel. C'est la user story du cahier des charges — « justifier le
calcul » — et sans l'article, il n'y a rien a justifier.

AUCUN CALCUL N'EST CONSERVE. Les montants qu'un cabinet saisit sont
ceux de ses clients ; les stocker serait une prise de risque gratuite.
La requete calcule, repond, et oublie.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependances import utilisateur_courant
from app.models import Utilisateur
from app.schemas import CalculateurDisponible, CalculEntree, ResultatCalcul
from app.services.calculateurs import (
    CalculRefuse,
    bareme,
    calculer_impot_progressif,
    calculer_impot_proportionnel,
    calculer_patente,
    calculer_tva,
    lire_article,
    tarif,
    taux,
)

journal = logging.getLogger(__name__)

routeur = APIRouter(tags=["calculateurs"])

# ---------------------------------------------------------------------
# LES BAREMES
#
# Chaque valeur est declaree AVEC l'article du CGI qui doit la porter.
# Ce n'est pas la source de verite : au moment du calcul, l'article est
# relu en base et la valeur y est cherchee. Si elle n'y figure plus —
# loi de finances, correction du corpus — le calcul est REFUSE.
#
# Autrement dit : ce bloc est une affirmation que le corpus valide ou
# dement. Il ne peut pas mentir en silence.
#
# POUR METTRE A JOUR APRES UNE LOI DE FINANCES : corriger la valeur ici,
# recharger le CGI, et relancer les tests. Si les deux ne concordent
# pas, tout calcul concerne s'arrete avec un message nommant l'article.
# ---------------------------------------------------------------------

# Les centimes additionnels communaux. L'article C 53 les institue sur
# l'IRPP, l'IS et la TVA ; l'article C 54 en fixe le taux. Ils sont
# declares une fois et partages : c'est le meme prelevement, et deux
# declarations finiraient par diverger.
CENTIMES_COMMUNAUX = taux(
    "centimes_additionnels",
    "Centimes additionnels communaux",
    "10",
    "C 54",
)

BAREMES: dict[str, dict] = {
    "tva": {
        "libelle": "TVA (taxe sur la valeur ajoutée)",
        "description": "Liquidation à partir d'un montant hors taxes ou toutes taxes comprises.",
        "parametre": taux(
            "tva_taux_general",
            "Taux général de la TVA",
            "17,5",
            "142",
        ),
        "centimes": CENTIMES_COMMUNAUX,
    },
    "is": {
        "libelle": "IS (impôt sur les sociétés)",
        "description": "Impôt assis sur le résultat fiscal de l'exercice.",
        "parametre": taux(
            "is_taux_normal",
            "Taux de l'impôt sur les sociétés",
            "30",
            "17",
        ),
        "centimes": CENTIMES_COMMUNAUX,
        "libelle_base": "Résultat fiscal",
        "intitule": "Impôt sur les sociétés",
    },
    "irpp": {
        "libelle": "IRPP (impôt sur le revenu des personnes physiques)",
        "description": (
            "Barème progressif applicable aux traitements, salaires, "
            "pensions et rentes viagères."
        ),
        # L'IRPP des salariés ne s'applique PAS à taux unique : l'article
        # 69 le calcule par tranches. Un taux moyen serait faux pour
        # tout le monde sauf par hasard.
        "bareme": bareme(
            "irpp_salaries",
            "Barème de l'IRPP sur les salaires",
            [
                ("2000000", "10"),
                ("3000000", "15"),
                ("5000000", "25"),
                (None, "35"),
            ],
            "69",
        ),
        "centimes": CENTIMES_COMMUNAUX,
        "libelle_base": "Revenu net imposable",
        "intitule": "Impôt sur le revenu",
    },
    "patente": {
        "libelle": "Contribution des patentes",
        "description": (
            "Taux sur le chiffre d'affaires du dernier exercice clos, "
            "encadré par un plancher et un plafond selon la taille de "
            "l'entreprise."
        ),
        # Trois tarifs distincts. Le PLANCHER et le PLAFOND ne sont pas
        # décoratifs : ils mordent précisément sur les très petites et
        # les très grandes entreprises, où le seul produit du taux
        # serait faux.
        "tarifs": {
            "grande": tarif(
                "grande",
                "Grandes entreprises",
                "0,159",
                "5000000",
                "2500000000",
                "2,5 milliards",
                "C 13",
            ),
            "moyenne": tarif(
                "moyenne",
                "Moyennes entreprises",
                "0,283",
                "141500",
                "4500000",
                "4 500 000",
                "C 13",
            ),
            "petite": tarif(
                "petite",
                "Petites entreprises",
                "0,494",
                "50000",
                "140000",
                "140 000",
                "C 13",
            ),
        },
    },
}


@routeur.get("/calculateurs")
def lister_calculateurs(db: Session = Depends(get_db)) -> list[CalculateurDisponible]:
    """Les calculateurs disponibles, et l'etat de leur base legale.

    `disponible` dit si l'article qui fonde le bareme est reellement
    dans le corpus. Une interface qui proposerait un calculateur sans
    base legale enverrait l'utilisateur vers un refus : autant le lui
    dire avant qu'il saisisse ses montants.
    """
    sortie = []
    for cle, regle in BAREMES.items():
        # Un calculateur est fonde soit sur un taux unique, soit sur un
        # bareme progressif : les deux portent leur numero d'article au
        # meme endroit.
        fondement = (
            regle.get("parametre")
            or regle.get("bareme")
            or next(iter(regle["tarifs"].values()))
        )
        try:
            lire_article(db, fondement.numero_article)
            disponible, motif = True, None
        except CalculRefuse as erreur:
            disponible, motif = False, str(erreur)

        sortie.append(
            {
                "cle": cle,
                "libelle": regle["libelle"],
                "description": regle["description"],
                "sigle": "CGI",
                "numero_article": fondement.numero_article,
                "disponible": disponible,
                "indisponible_parce_que": motif,
            }
        )
    return sortie


def _refus(erreur: CalculRefuse) -> HTTPException:
    """Un refus de calcul est une reponse metier, pas une panne.

    422 et non 500 : le client doit pouvoir afficher le motif tel quel
    a l'utilisateur, qui est souvent le seul a pouvoir agir dessus.
    """
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erreur))


@routeur.post("/calculateurs/tva")
def liquider_tva(
    corps: CalculEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> ResultatCalcul:
    """Liquidation de la TVA, depuis un montant HT ou TTC."""
    try:
        return calculer_tva(
            db,
            corps.montant,
            corps.sur_ttc,
            BAREMES["tva"]["parametre"],
            BAREMES["tva"].get("centimes"),
        )
    except CalculRefuse as erreur:
        raise _refus(erreur) from erreur


@routeur.post("/calculateurs/is")
def liquider_is(
    corps: CalculEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> ResultatCalcul:
    """Impot sur les societes, assis sur le resultat fiscal."""
    bareme = BAREMES["is"]
    try:
        return calculer_impot_proportionnel(
            db,
            corps.montant,
            bareme["parametre"],
            bareme["intitule"],
            bareme["libelle_base"],
            bareme.get("centimes"),
        )
    except CalculRefuse as erreur:
        raise _refus(erreur) from erreur


@routeur.post("/calculateurs/irpp")
def liquider_irpp(
    corps: CalculEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> ResultatCalcul:
    """Impot sur le revenu des personnes physiques, par tranches."""
    regle = BAREMES["irpp"]
    try:
        return calculer_impot_progressif(
            db,
            corps.montant,
            regle["bareme"],
            regle["intitule"],
            regle["libelle_base"],
            regle.get("centimes"),
        )
    except CalculRefuse as erreur:
        raise _refus(erreur) from erreur


@routeur.post("/calculateurs/patente")
def liquider_patente(
    corps: CalculEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> ResultatCalcul:
    """Contribution des patentes, selon la taille de l'entreprise."""
    tarifs = BAREMES["patente"]["tarifs"]
    categorie = (corps.categorie or "moyenne").lower()
    if categorie not in tarifs:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Catégorie inconnue. Valeurs acceptées : {', '.join(tarifs)}.",
        )
    try:
        return calculer_patente(db, corps.montant, tarifs[categorie])
    except CalculRefuse as erreur:
        raise _refus(erreur) from erreur
