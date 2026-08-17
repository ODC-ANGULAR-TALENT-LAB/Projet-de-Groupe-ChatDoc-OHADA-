"""Hachage des mots de passe et jetons de session.

bcrypt cout 12 : aucune recuperation en clair n'est possible.
JWT court (30 minutes par defaut).

ECART PAR RAPPORT AU GUIDE : la bibliotheque bcrypt est utilisee
directement, sans passlib. passlib n'a plus de version depuis 2020 et
casse a l'import avec bcrypt 5 (il lit un attribut __about__ qui
n'existe plus). Une couche d'abstraction qui empeche de mettre a jour
la brique qu'elle abstrait ne rend plus service.
"""

from __future__ import annotations

import base64
import datetime
import hashlib

import bcrypt
from jose import JWTError, jwt

from app.config import parametres

ALGORITHME = "HS256"

# Cout 12 : le reglage retenu par le document d'architecture. Plus eleve
# ralentit chaque connexion, plus bas affaiblit les empreintes.
COUT_BCRYPT = 12


def _preparer(mot_de_passe: str) -> bytes:
    """Ramene le mot de passe a une longueur que bcrypt accepte.

    bcrypt refuse au-dela de 72 octets. Tronquer serait le pire choix :
    deux mots de passe partageant leurs 72 premiers octets deviendraient
    interchangeables, sans que personne s'en apercoive. On condense donc
    d'abord en SHA-256, dont la sortie encodee tient toujours en 44
    octets, quelle que soit la longueur d'origine.
    """
    condensat = hashlib.sha256(mot_de_passe.encode("utf-8")).digest()
    return base64.b64encode(condensat)


def hacher(mot_de_passe: str) -> str:
    empreinte = bcrypt.hashpw(_preparer(mot_de_passe), bcrypt.gensalt(COUT_BCRYPT))
    return empreinte.decode("ascii")


def verifier(mot_de_passe: str, empreinte: str) -> bool:
    try:
        return bcrypt.checkpw(_preparer(mot_de_passe), empreinte.encode("ascii"))
    except ValueError:
        # Empreinte malformee en base : on refuse, on ne laisse pas
        # l'exception remonter jusqu'a l'utilisateur.
        return False


def creer_jeton(utilisateur_id: int) -> str:
    """Jeton de session porteur de l'identifiant utilisateur."""
    expiration = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=parametres.jwt_expiration_minutes
    )
    return jwt.encode(
        {"sub": str(utilisateur_id), "exp": expiration},
        parametres.jwt_secret,
        algorithm=ALGORITHME,
    )


def lire_jeton(jeton: str) -> int | None:
    """Identifiant contenu dans le jeton, ou None s'il est invalide."""
    try:
        charge = jwt.decode(jeton, parametres.jwt_secret, algorithms=[ALGORITHME])
        return int(charge["sub"])
    except (JWTError, KeyError, ValueError):
        return None
