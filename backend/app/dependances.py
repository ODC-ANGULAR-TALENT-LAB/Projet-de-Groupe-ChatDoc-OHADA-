"""Dependances FastAPI partagees par les routeurs."""

from __future__ import annotations

import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Utilisateur
from app.services.securite import lire_jeton

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
    """Remet le quota a son plafond au passage du mois.

    Reinitialisation PAR DATE, pas par compteur : on compare le mois de
    la derniere remise a zero au mois courant. Un compteur glissant
    derive des que l'utilisateur change de rythme.
    """
    aujourd_hui = datetime.date.today()
    derniere = utilisateur.quota_reinit_le

    if derniere is None or (derniere.year, derniere.month) < (
        aujourd_hui.year,
        aujourd_hui.month,
    ):
        utilisateur.quota_restant = QUOTA_PAR_PLAN.get(utilisateur.plan, 5)
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


# Quota mensuel par plan. Le socle est freemium : 5 questions par mois.
QUOTA_PAR_PLAN = {"gratuit": 5}
