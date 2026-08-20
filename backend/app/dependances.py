"""Dependances FastAPI partagees par les routeurs."""

from __future__ import annotations

import datetime
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Utilisateur
from app.services.forfaits import QUOTA_PAR_PLAN, credits_du_plan
from app.services.securite import lire_jeton

journal = logging.getLogger(__name__)

schema_jeton = HTTPBearer(auto_error=False)


def utilisateur_courant(
    identifiants: HTTPAuthorizationCredentials | None = Depends(schema_jeton),
    db: Session = Depends(get_db),
) -> Utilisateur:
    """L'utilisateur porte par le jeton, ou 401."""
    refus = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if identifiants is None:
        raise refus

    utilisateur_id = lire_jeton(identifiants.credentials)
    if utilisateur_id is None:
        raise refus

    utilisateur = db.get(Utilisateur, utilisateur_id)
    if utilisateur is None:
        raise refus

    return reinitialiser_quota_si_besoin(db, utilisateur)


def reinitialiser_quota_si_besoin(db: Session, utilisateur: Utilisateur) -> Utilisateur:
    """Fait retomber l'abonnement echu, puis remet les credits au plafond.

    L'ORDRE COMPTE. L'echeance est traitee AVANT la remise a zero :
    sinon, un abonnement expire le mois dernier se verrait recharger au
    plafond du forfait payant avant d'etre retrograde, offrant un mois
    entier de credits non payes.

    Reinitialisation PAR DATE, pas par compteur : on compare le mois de
    la derniere remise a zero au mois courant. Un compteur glissant
    derive des que l'utilisateur change de rythme.
    """
    aujourd_hui = datetime.date.today()

    # 1. L'abonnement paye est-il encore valide ?
    #
    # Sans ce controle, un paiement unique ouvrirait le forfait pour
    # toujours : les credits se rechargent chaque mois et rien ne dirait
    # que le mois paye est ecoule.
    echu = (
        utilisateur.plan != "gratuit"
        and utilisateur.plan_echeance is not None
        and utilisateur.plan_echeance < aujourd_hui
    )
    if echu:
        journal.info(
            "Abonnement %s echu le %s : retour au forfait gratuit (compte %s).",
            utilisateur.plan,
            utilisateur.plan_echeance,
            utilisateur.id,
        )
        utilisateur.plan = "gratuit"
        utilisateur.plan_echeance = None
        # On force la remise a zero : le compte doit repartir sur les
        # credits du gratuit, pas conserver ceux qu'il lui restait.
        utilisateur.quota_restant = credits_du_plan("gratuit")
        utilisateur.quota_reinit_le = aujourd_hui
        db.commit()
        return utilisateur

    # 2. Passage du mois : les credits reviennent a leur plafond.
    derniere = utilisateur.quota_reinit_le
    if derniere is None or (derniere.year, derniere.month) < (
        aujourd_hui.year,
        aujourd_hui.month,
    ):
        utilisateur.quota_restant = credits_du_plan(utilisateur.plan)
        utilisateur.quota_reinit_le = aujourd_hui
        db.commit()

    return utilisateur


def administrateur(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
) -> Utilisateur:
    """Reserve la route aux administrateurs de l'application.

    403 plutot que 404 : l'utilisateur est authentifie, il manque
    seulement le droit. Masquer l'existence du back-office n'apporterait
    rien — il est documente dans /docs — et compliquerait le diagnostic.
    """
    if not utilisateur.est_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Cette action est reservee aux administrateurs de l'application.",
        )
    return utilisateur


def redacteur_corpus(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
) -> Utilisateur:
    """Reserve la route aux juristes (et aux administrateurs).

    C'EST UN DROIT PROFESSIONNEL, PAS UN DROIT TECHNIQUE. Valider un
    texte, c'est engager sa signature : le nom du validateur figure dans
    la table de provenance publiee, et c'est lui qui repond d'une
    citation contestee. D'ou un role distinct de l'administration de
    l'application, qui attribue les roles mais n'a aucune legitimite a
    se prononcer sur un texte de loi.
    """
    if not utilisateur.redige_le_corpus:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Cet espace est reserve aux juristes responsables du corpus.",
        )
    return utilisateur


# QUOTA_PAR_PLAN vit desormais dans services/forfaits.py, aux cotes des
# prix et de la marge : le nombre de credits et ce qu'il coute ne
# doivent pas pouvoir diverger. Reexporte ici pour le code qui l'importe
# depuis ce module.
__all__ = ['QUOTA_PAR_PLAN', 'credits_du_plan', 'utilisateur_courant',
           'administrateur', 'redacteur_corpus',
           'reinitialiser_quota_si_besoin', 'get_db']
