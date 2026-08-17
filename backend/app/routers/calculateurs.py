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
    calculer_impot_proportionnel,
    calculer_tva,
    lire_article,
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
    for cle, bareme in BAREMES.items():
        parametre = bareme["parametre"]
        try:
            lire_article(db, parametre.numero_article)
            disponible, motif = True, None
        except CalculRefuse as erreur:
            disponible, motif = False, str(erreur)

        sortie.append(
            {
                "cle": cle,
                "libelle": bareme["libelle"],
                "description": bareme["description"],
                "sigle": "CGI",
                "numero_article": parametre.numero_article,
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
