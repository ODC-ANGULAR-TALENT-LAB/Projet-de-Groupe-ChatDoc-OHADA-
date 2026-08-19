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

import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependances import utilisateur_courant
from app.models import Utilisateur
from app.schemas import ProfilEntree, ProfilSortie
from app.services.profil import (
    PREFERENCES,
    TAILLE_MAXIMALE_PHOTO,
    preparer_photo,
    ProfilRefuse,
    initiales,
    nettoyer_prenom,
    preferences_completes,
    valider_preferences,
)

journal = logging.getLogger(__name__)

routeur = APIRouter(tags=["profil"])


def _adresse_photo(utilisateur: Utilisateur) -> str | None:
    """Ou l'interface doit-elle chercher l'avatar ?

    TROIS NIVEAUX, DANS CET ORDRE : la photo televersee, puis celle du
    compte Google, puis rien — l'interface affiche alors les initiales.
    Le choix de l'utilisateur prime sur celui de Google, qui n'est
    qu'un defaut.

    L'URL interne porte la DATE du televersement. Sans elle, le
    navigateur garderait l'ancienne image en cache et l'utilisateur
    croirait son changement perdu.
    """
    if utilisateur.photo is not None:
        jeton = int((utilisateur.photo_le or datetime.datetime.now()).timestamp())
        return f"/utilisateurs/{utilisateur.id}/photo?v={jeton}"
    return utilisateur.photo_url


def _en_sortie(utilisateur: Utilisateur) -> dict:
    return {
        "email": utilisateur.email,
        "prenom": utilisateur.prenom,
        "photo_url": _adresse_photo(utilisateur),
        "photo_televersee": utilisateur.photo is not None,
        "photo_google": utilisateur.photo_url,
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


@routeur.put("/moi/photo")
async def televerser_photo(
    fichier: UploadFile = File(...),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> ProfilSortie:
    """Remplace l'avatar par l'image envoyée.

    L'IMAGE EST ENTIÈREMENT RÉÉCRITE avant d'être stockée : recadrée au
    carré, ramenée à 256 px, convertie en WebP. Ce n'est pas seulement
    une question de poids — une image réencodée perd ses métadonnées
    EXIF, dont la position GPS de la prise de vue, qu'un utilisateur ne
    pense jamais publier en changeant sa photo de profil.
    """
    contenu = await fichier.read()
    if len(contenu) > TAILLE_MAXIMALE_PHOTO:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"L'image dépasse {TAILLE_MAXIMALE_PHOTO // (1024 * 1024)} Mo.",
        )

    try:
        utilisateur.photo = preparer_photo(contenu)
    except ProfilRefuse as erreur:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(erreur)
        ) from erreur
    finally:
        # Le fichier d'origine ne survit pas à la requête : il n'est
        # écrit nulle part, et seule sa version réencodée est conservée.
        contenu = b""

    utilisateur.photo_type = "image/webp"
    utilisateur.photo_le = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    db.refresh(utilisateur)
    journal.info("Photo de profil mise a jour pour %s.", utilisateur.email)
    return _en_sortie(utilisateur)


@routeur.delete("/moi/photo")
def retirer_photo(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> ProfilSortie:
    """Supprime l'avatar téléversé.

    ON NE TOUCHE PAS À `photo_url` : retirer sa propre photo doit
    rendre celle du compte Google, pas les initiales. C'est la raison
    d'être des deux colonnes.
    """
    utilisateur.photo = None
    utilisateur.photo_type = None
    utilisateur.photo_le = None
    db.commit()
    db.refresh(utilisateur)
    return _en_sortie(utilisateur)


@routeur.get("/utilisateurs/{utilisateur_id}/photo")
def photo_de(utilisateur_id: int, db: Session = Depends(get_db)) -> Response:
    """Sert un avatar téléversé.

    ROUTE PUBLIQUE, ET C'EST ASSUMÉ : une balise <img> n'envoie pas le
    jeton d'authentification, et un avatar n'est pas un secret — il est
    destiné à être vu. Elle ne rend QUE l'image, jamais l'e-mail ni
    quoi que ce soit d'autre du compte.
    """
    ligne = db.get(Utilisateur, utilisateur_id)
    if ligne is None or ligne.photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucune photo.")

    return Response(
        content=ligne.photo,
        media_type=ligne.photo_type or "image/webp",
        headers={
            # Un an de cache : l'URL porte la date du téléversement, donc
            # une nouvelle photo a une nouvelle URL. Rien à invalider.
            "Cache-Control": "public, max-age=31536000, immutable"
        },
    )
