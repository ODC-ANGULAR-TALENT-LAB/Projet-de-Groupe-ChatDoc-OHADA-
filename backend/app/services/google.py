"""Verification des jetons d'identite Google.

Le navigateur obtient un jeton d'identite signe par Google, puis
l'envoie a cette API. On ne fait JAMAIS confiance a ce que le
navigateur affirme : le jeton est verifie cote serveur contre les cles
publiques de Google, et c'est son contenu qui fait foi.

POURQUOI PAS DE CODE SECRET ICI. Le secret sert au flux "code
d'autorisation", pour agir au nom de l'utilisateur sur les API Google.
Ici on veut seulement l'authentifier : verifier la signature du jeton
suffit, et n'expose aucun secret supplementaire.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from google.auth.transport import requests as transport_google
from google.oauth2 import id_token as jeton_google

from app.config import parametres

journal = logging.getLogger(__name__)

# Emetteurs legitimes d'un jeton d'identite Google.
EMETTEURS = ("accounts.google.com", "https://accounts.google.com")


class JetonGoogleInvalide(Exception):
    """Le jeton presente n'est pas exploitable."""


@dataclass(frozen=True)
class IdentiteGoogle:
    """Ce que Google atteste, une fois la signature verifiee."""

    sub: str
    email: str


def verifier_jeton(jeton: str) -> IdentiteGoogle:
    """Verifie un jeton d'identite et en extrait l'identite.

    Leve JetonGoogleInvalide si la signature, l'emetteur, le
    destinataire ou l'expiration ne conviennent pas.
    """
    if not parametres.google_client_id:
        raise JetonGoogleInvalide(
            "GOOGLE_CLIENT_ID absent du .env : la connexion Google est "
            "desactivee sur ce serveur."
        )

    try:
        # Verifie la signature contre les cles publiques de Google, et
        # que le jeton nous est bien destine (claim "aud" == client ID).
        # Un jeton emis pour une autre application est rejete : sans ce
        # controle, n'importe quel site utilisant Google pourrait
        # fabriquer une session ici.
        charge = jeton_google.verify_oauth2_token(
            jeton,
            transport_google.Request(),
            parametres.google_client_id,
        )
    except ValueError as erreur:
        # Signature invalide, jeton expire, destinataire incorrect.
        journal.warning("Jeton Google rejete : %s", erreur)
        raise JetonGoogleInvalide("Jeton Google invalide ou expire.") from erreur

    if charge.get("iss") not in EMETTEURS:
        raise JetonGoogleInvalide("Emetteur du jeton inattendu.")

    email = charge.get("email")
    if not email:
        raise JetonGoogleInvalide("Le jeton ne porte pas d'adresse e-mail.")

    # Sans e-mail verifie, on ne rattache PAS le compte : une adresse non
    # verifiee permettrait de prendre la main sur un compte existant en
    # se declarant proprietaire de son adresse.
    if not charge.get("email_verified"):
        raise JetonGoogleInvalide(
            "Cette adresse Google n'est pas verifiee. Verifiez-la chez "
            "Google, ou creez un compte avec un mot de passe."
        )

    return IdentiteGoogle(sub=charge["sub"], email=email)
