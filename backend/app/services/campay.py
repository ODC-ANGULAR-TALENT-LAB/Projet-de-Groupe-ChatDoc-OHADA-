"""Encaissement Mobile Money via CamPay.

CE QUE L'APPLICATION NE VOIT JAMAIS : le code secret du payeur. Le flux
« collect » de CamPay pousse une invite USSD sur le telephone de
l'abonne, qui valide sur SON appareil, aupres de SON operateur. Nous
n'envoyons qu'un numero et un montant, et nous recevons un etat. Aucun
secret de paiement ne transite par ce service, et aucun n'y est stocke.

Un numero de telephone n'est pas un secret : c'est un identifiant, au
meme titre qu'une adresse e-mail. Il est conserve avec la demande parce
qu'un litige sur un paiement se tranche avec lui.

CONTRAT DE L'API, releve sur le SDK officiel :

    POST /api/token/                 {username, password}
                                  -> {token, expires_in}
    POST /api/collect/               {amount, currency, from,
                                      description, external_reference}
                                  -> {reference, ussd_code, operator}
    GET  /api/transaction/{ref}/  -> {reference, status, amount, ...}

    En-tete : Authorization: Token <jeton>
    Etats   : PENDING | SUCCESSFUL | FAILED

LE MONTANT N'EST JAMAIS FOURNI PAR LE CLIENT. Il est lu dans le
catalogue, cote serveur, a partir du seul code de forfait. Accepter un
montant depuis le navigateur reviendrait a laisser choisir son prix.
"""

from __future__ import annotations

import logging
import threading
import time

import httpx
from jose import JWTError, jwt

from app.config import parametres

journal = logging.getLogger(__name__)

DELAI = 20.0

# Etats renvoyes par CamPay.
EN_ATTENTE = "PENDING"
REUSSI = "SUCCESSFUL"
ECHOUE = "FAILED"


class PaiementIndisponible(RuntimeError):
    """CamPay n'est pas joignable ou pas configure."""


class PaiementRefuse(ValueError):
    """La demande de paiement a ete rejetee (numero invalide, etc.)."""


# ---------------------------------------------------------------------
# Jeton
#
# Il vaut une heure environ. Le redemander a chaque appel ajouterait un
# aller-retour a chaque paiement, et CamPay finirait par nous limiter.
# Un verrou protege le renouvellement : sans lui, deux paiements
# simultanes sur un compte fraichement demarre demanderaient deux jetons.
# ---------------------------------------------------------------------

_verrou = threading.Lock()
_jeton: str | None = None
_expire_a: float = 0.0


def _entetes() -> dict[str, str]:
    return {
        "Authorization": f"Token {_obtenir_jeton()}",
        "Content-Type": "application/json",
    }


def _obtenir_jeton() -> str:
    global _jeton, _expire_a

    with _verrou:
        # 60 secondes de marge : un jeton qui expire pendant le vol
        # ferait echouer un paiement pour rien.
        if _jeton and time.monotonic() < _expire_a - 60:
            return _jeton

        if not parametres.campay_configure:
            raise PaiementIndisponible(
                "Le paiement mobile n'est pas configure sur ce serveur."
            )

        try:
            reponse = httpx.post(
                f"{parametres.campay_url}/api/token/",
                json={
                    "username": parametres.campay_username,
                    "password": parametres.campay_password,
                },
                timeout=DELAI,
            )
            reponse.raise_for_status()
            corps = reponse.json()
        except (httpx.HTTPError, ValueError) as erreur:
            raise PaiementIndisponible(
                "Le service de paiement ne repond pas."
            ) from erreur

        _jeton = corps["token"]
        _expire_a = time.monotonic() + float(corps.get("expires_in", 3600))
        return _jeton


def oublier_jeton() -> None:
    """Vide le jeton en cache. Utile aux tests et apres un 401."""
    global _jeton, _expire_a
    with _verrou:
        _jeton, _expire_a = None, 0.0


# ---------------------------------------------------------------------
# Numero de telephone
# ---------------------------------------------------------------------


def normaliser_numero(numero: str) -> str:
    """Ramene un numero camerounais a la forme attendue par CamPay.

    CamPay veut 237XXXXXXXXX. Les gens ecrivent « 6 99 00 00 00 »,
    « +237699000000 », « 00237699000000 » : refuser ces formes ferait
    echouer des paiements pour une question de mise en page.
    """
    chiffres = "".join(c for c in (numero or "") if c.isdigit())

    if chiffres.startswith("00237"):
        chiffres = chiffres[2:]
    if len(chiffres) == 9 and chiffres[0] == "6":
        chiffres = "237" + chiffres
    if not (chiffres.startswith("237") and len(chiffres) == 12):
        raise PaiementRefuse(
            "Numero invalide. Attendu : un numero camerounais a neuf "
            "chiffres commencant par 6."
        )
    return chiffres


# ---------------------------------------------------------------------
# Collecte
# ---------------------------------------------------------------------


def collecter(
    montant: int, numero: str, description: str, reference_externe: str
) -> dict:
    """Demande le paiement, et rend de quoi guider l'abonne.

    La reponse porte `ussd_code` : le code a composer si l'invite
    n'apparait pas d'elle-meme sur le telephone. L'afficher evite le
    scenario ou l'abonne attend un ecran qui ne vient pas.
    """
    numero = normaliser_numero(numero)

    try:
        reponse = httpx.post(
            f"{parametres.campay_url}/api/collect/",
            json={
                "amount": str(int(montant)),
                "currency": "XAF",
                "from": numero,
                "description": description,
                "external_reference": reference_externe,
            },
            headers=_entetes(),
            timeout=DELAI,
        )
    except httpx.HTTPError as erreur:
        raise PaiementIndisponible("Le service de paiement ne repond pas.") from erreur

    if reponse.status_code >= 400:
        journal.warning(
            "CamPay a refuse la collecte (%s) : %s",
            reponse.status_code,
            reponse.text[:300],
        )
        raise PaiementRefuse(
            "Le paiement n'a pas pu etre lance. Verifiez le numero et reessayez."
        )

    corps = reponse.json()
    return {
        "reference": corps["reference"],
        "code_ussd": corps.get("ussd_code"),
        "operateur": corps.get("operator"),
        "numero": numero,
    }


def etat(reference: str) -> dict:
    """L'etat d'une transaction, tel que CamPay le donne.

    C'EST LA SOURCE DE VERITE. Ni le navigateur ni le rappel non signe
    ne peuvent affirmer qu'un paiement a abouti : seule cette lecture,
    faite par le serveur aupres de CamPay, l'etablit.
    """
    try:
        reponse = httpx.get(
            f"{parametres.campay_url}/api/transaction/{reference}/",
            headers=_entetes(),
            timeout=DELAI,
        )
        reponse.raise_for_status()
    except httpx.HTTPError as erreur:
        raise PaiementIndisponible("Le service de paiement ne repond pas.") from erreur

    corps = reponse.json()
    return {
        "reference": corps.get("reference", reference),
        "statut": corps.get("status", EN_ATTENTE),
        "operateur": corps.get("operator"),
        "reference_operateur": corps.get("operator_reference"),
    }


# ---------------------------------------------------------------------
# Rappel signe
# ---------------------------------------------------------------------


def signature_valide(signature: str) -> bool:
    """Le rappel vient-il reellement de CamPay ?

    SANS CETTE VERIFICATION, LE RAPPEL EST UNE PORTE OUVERTE : l'URL est
    publique par nature, et il suffirait d'y poster un « SUCCESSFUL »
    pour s'offrir un abonnement. La signature est un JWT signe avec la
    cle du webhook, connue de CamPay et de nous seuls.

    Faute de cle configuree, on refuse. Accepter « en attendant » est
    exactement la configuration qu'on oublie de refermer.
    """
    cle = (parametres.campay_webhook_cle or "").strip()
    if not cle or not signature:
        return False
    try:
        jwt.decode(signature, cle, algorithms=["HS256"])
        return True
    except JWTError:
        journal.warning("Rappel CamPay rejete : signature invalide.")
        return False
