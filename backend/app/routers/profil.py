"""Profil de l'utilisateur et parametres.

UNE SEULE ROUTE POUR LIRE, UNE POUR ECRIRE. Le profil est petit et se
lit d'un bloc : eclater prenom, photo et preferences en trois routes
obligerait l'interface a trois appels pour dessiner un ecran.

RIEN N'EST MODIFIABLE ICI QUI ENGAGE LE SERVICE. Le plan, le quota et
le role ne se changent pas depuis le profil : ce sont des decisions du
service, pas des preferences de l'utilisateur. Les exposer en lecture
seule evite d'avoir a expliquer pourquoi le champ ne s'enregistre pas.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependances import utilisateur_courant
from app.models import Utilisateur
from app.schemas import ProfilEntree, ProfilSortie
from app.services.profil import (
    PREFERENCES,
    ProfilRefuse,
    initiales,
    nettoyer_prenom,
    preferences_completes,
    valider_preferences,
)

journal = logging.getLogger(__name__)

routeur = APIRouter(tags=["profil"])


def _en_sortie(utilisateur: Utilisateur) -> dict:
    return {
        "email": utilisateur.email,
        "prenom": utilisateur.prenom,
        "photo_url": utilisateur.photo_url,
        "initiales": initiales(utilisateur.prenom, utilisateur.email),
        "role": utilisateur.role,
        "plan": utilisateur.plan,
        "quota_restant": utilisateur.quota_restant,
        # Le compte a-t-il un mot de passe ? L'interface en a besoin
        # pour savoir s'il faut proposer « changer de mot de passe » —
        # un compte Google n'en a pas.
        "connexion_google": utilisateur.google_sub is not None,
        "cgu_version": utilisateur.cgu_version,
        "cgu_acceptees_le": utilisateur.cgu_acceptees_le,
        "preferences": preferences_completes(utilisateur.preferences),
    }


@routeur.get("/moi/profil")
def mon_profil(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
) -> ProfilSortie:
    """Le profil complet, préférences et défauts compris."""
    return _en_sortie(utilisateur)


@routeur.get("/moi/preferences/catalogue")
def catalogue_preferences() -> dict:
    """Les préférences réglables, avec leurs valeurs acceptées.

    L'INTERFACE NE DEVINE PAS LA LISTE. Elle la lit ici, si bien qu'une
    préférence ajoutée côté serveur apparaît sans qu'on touche au
    frontend — et surtout, les deux ne peuvent pas diverger.
    """
    return {
        cle: {
            "type": "booleen" if regle["type"] is bool else "texte",
            "defaut": regle["defaut"],
            "valeurs": regle.get("valeurs"),
        }
        for cle, regle in PREFERENCES.items()
    }


@routeur.put("/moi/profil")
def enregistrer_profil(
    corps: ProfilEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> ProfilSortie:
    """Met à jour le prénom et les préférences.

    LES CHAMPS ABSENTS NE SONT PAS TOUCHÉS. Envoyer seulement les
    préférences ne doit pas effacer le prénom : une interface qui
    n'affiche qu'une partie du profil ne doit pas pouvoir détruire le
    reste par omission.
    """
    try:
        if corps.prenom is not None:
            utilisateur.prenom = nettoyer_prenom(corps.prenom)
        if corps.preferences is not None:
            retenues = valider_preferences(corps.preferences)
            # On FUSIONNE : le client peut n'envoyer que ce qu'il change.
            utilisateur.preferences = {
                **(utilisateur.preferences or {}),
                **retenues,
            }
    except ProfilRefuse as erreur:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(erreur)
        ) from erreur

    db.commit()
    db.refresh(utilisateur)
    journal.info("Profil mis a jour pour %s.", utilisateur.email)
    return _en_sortie(utilisateur)
