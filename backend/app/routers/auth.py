"""Comptes : inscription, connexion, quota."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import parametres
from app.db import get_db
from app.dependances import QUOTA_PAR_PLAN, utilisateur_courant
from app.models import Utilisateur
from app.schemas import Identifiants, Inscription, Jeton, JetonGoogle, Quota
from app.services.google import JetonGoogleInvalide, verifier_jeton
from app.services.securite import creer_jeton, hacher, verifier

routeur = APIRouter(tags=["comptes"])


def _jeton(utilisateur: Utilisateur) -> Jeton:
    return Jeton(
        jeton_acces=creer_jeton(utilisateur.id),
        expire_dans_minutes=parametres.jwt_expiration_minutes,
    )


@routeur.post("/auth/inscription", status_code=status.HTTP_201_CREATED)
def inscription(corps: Inscription, db: Session = Depends(get_db)) -> Jeton:
    """Cree un compte. LES CONDITIONS DOIVENT AVOIR ETE ACCEPTEES.

    LE REFUS EST COTE SERVEUR, pas seulement dans le formulaire. Une
    case desactivee dans le navigateur n'engage rien : elle se
    contourne avec deux lignes de console. Le seul endroit ou
    l'acceptation peut etre exigee est ici.

    On enregistre AVEC LA VERSION ET LA DATE. « A accepte » ne prouve
    rien le jour ou il faudrait le prouver : accepte quand, et accepte
    quoi ? Pour ce produit ce n'est pas theorique — le cahier des
    charges (§3) exclut toute garantie de resultat, et la seule reponse
    solide a « je l'ai pris pour un conseil juridique » est la date et
    la version des conditions acceptees.
    """
    if not corps.cgu_acceptees:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Les conditions générales d'utilisation doivent être acceptées "
            "pour créer un compte.",
        )

    existant = db.scalar(select(Utilisateur).where(Utilisateur.email == corps.email))
    if existant is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet e-mail est deja inscrit")

    utilisateur = Utilisateur(
        email=corps.email,
        mot_de_passe_hash=hacher(corps.mot_de_passe),
        plan="gratuit",
        quota_restant=QUOTA_PAR_PLAN["gratuit"],
        quota_reinit_le=datetime.date.today(),
        cgu_version=parametres.version_cgu,
        cgu_acceptees_le=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(utilisateur)
    db.commit()
    db.refresh(utilisateur)
    return _jeton(utilisateur)


@routeur.post("/auth/connexion")
def connexion(corps: Identifiants, db: Session = Depends(get_db)) -> Jeton:
    utilisateur = db.scalar(select(Utilisateur).where(Utilisateur.email == corps.email))

    # Meme message dans les trois cas : distinguer "e-mail inconnu",
    # "compte sans mot de passe" et "mot de passe faux" revient a
    # publier la liste des comptes et leur mode de connexion.
    if (
        utilisateur is None
        or utilisateur.mot_de_passe_hash is None
        or not verifier(corps.mot_de_passe, utilisateur.mot_de_passe_hash)
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Identifiants invalides"
        )

    return _jeton(utilisateur)


@routeur.post("/auth/google")
def connexion_google(corps: JetonGoogle, db: Session = Depends(get_db)) -> Jeton:
    """Inscription ou connexion par compte Google.

    Une seule route pour les deux : Google atteste déjà de l'identité,
    demander à l'utilisateur s'il « a déjà un compte » n'apporterait
    rien qu'on ne sache pas.
    """
    try:
        identite = verifier_jeton(corps.jeton_identite)
    except JetonGoogleInvalide as erreur:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(erreur)) from erreur

    # 1. Compte déjà rattaché à ce compte Google.
    utilisateur = db.scalar(
        select(Utilisateur).where(Utilisateur.google_sub == identite.sub)
    )

    if utilisateur is None:
        # 2. Un compte existe avec cette adresse : on le rattache.
        #    Sûr parce que Google a vérifié l'adresse (contrôlé dans
        #    verifier_jeton) — l'utilisateur en est bien propriétaire.
        #    Le mot de passe existant reste valable : les deux moyens
        #    de connexion coexistent.
        utilisateur = db.scalar(
            select(Utilisateur).where(Utilisateur.email == identite.email)
        )
        if utilisateur is not None:
            utilisateur.google_sub = identite.sub
        else:
            # 3. Aucun compte : on en crée un, sans mot de passe.
            utilisateur = Utilisateur(
                email=identite.email,
                mot_de_passe_hash=None,
                google_sub=identite.sub,
                plan="gratuit",
                quota_restant=QUOTA_PAR_PLAN["gratuit"],
                quota_reinit_le=datetime.date.today(),
            )
            db.add(utilisateur)

        db.commit()
        db.refresh(utilisateur)

    return _jeton(utilisateur)


@routeur.get("/moi/quota")
def mon_quota(utilisateur: Utilisateur = Depends(utilisateur_courant)) -> Quota:
    return Quota(
        quota_restant=utilisateur.quota_restant,
        quota_reinit_le=utilisateur.quota_reinit_le,
        plan=utilisateur.plan,
        role=utilisateur.role,
    )
