"""Tests de la vérification des jetons d'identité Google.

Le serveur ne fait aucune confiance à ce que le navigateur affirme.
Ces tests couvrent les cas où un jeton doit être rejeté — chacun
correspond à une façon d'ouvrir une session qui ne devrait pas l'être.
"""

from __future__ import annotations

import pytest

from app.config import parametres
from app.services import google
from app.services.google import JetonGoogleInvalide, verifier_jeton

CHARGE_VALIDE = {
    "iss": "https://accounts.google.com",
    "sub": "112233445566778899",
    "email": "juriste@exemple.cm",
    "email_verified": True,
}


@pytest.fixture(autouse=True)
def client_id_configure(monkeypatch):
    monkeypatch.setattr(parametres, "google_client_id", "client-de-test")


def brancher(monkeypatch, charge: dict | Exception) -> None:
    """Remplace l'appel à Google par une réponse contrôlée."""

    def faux_verify(*args, **kwargs):
        if isinstance(charge, Exception):
            raise charge
        return charge

    monkeypatch.setattr(google.jeton_google, "verify_oauth2_token", faux_verify)


def test_jeton_valide_donne_une_identite(monkeypatch):
    brancher(monkeypatch, CHARGE_VALIDE)

    identite = verifier_jeton("un-jeton")

    assert identite.sub == "112233445566778899"
    assert identite.email == "juriste@exemple.cm"


def test_signature_invalide_rejetee(monkeypatch):
    """verify_oauth2_token lève ValueError sur signature, expiration ou
    destinataire incorrects."""
    brancher(monkeypatch, ValueError("Token expired"))

    with pytest.raises(JetonGoogleInvalide):
        verifier_jeton("un-jeton-perime")


def test_email_non_verifie_rejete(monkeypatch):
    """Le point le plus sensible : sans e-mail vérifié, quelqu'un
    pourrait se déclarer propriétaire de l'adresse d'un tiers et
    prendre la main sur son compte."""
    brancher(monkeypatch, {**CHARGE_VALIDE, "email_verified": False})

    with pytest.raises(JetonGoogleInvalide, match="pas verifiee"):
        verifier_jeton("un-jeton")


def test_jeton_sans_email_rejete(monkeypatch):
    charge = {k: v for k, v in CHARGE_VALIDE.items() if k != "email"}
    brancher(monkeypatch, charge)

    with pytest.raises(JetonGoogleInvalide, match="adresse e-mail"):
        verifier_jeton("un-jeton")


def test_emetteur_inattendu_rejete(monkeypatch):
    brancher(monkeypatch, {**CHARGE_VALIDE, "iss": "https://mechant.example"})

    with pytest.raises(JetonGoogleInvalide, match="Emetteur"):
        verifier_jeton("un-jeton")


def test_sans_client_id_la_connexion_google_est_desactivee(monkeypatch):
    """Un serveur sans GOOGLE_CLIENT_ID ne peut pas vérifier le
    destinataire du jeton : il refuse plutôt que d'accepter n'importe
    quel jeton Google."""
    monkeypatch.setattr(parametres, "google_client_id", "")

    with pytest.raises(JetonGoogleInvalide, match="GOOGLE_CLIENT_ID"):
        verifier_jeton("un-jeton")


@pytest.mark.parametrize("emetteur", ["accounts.google.com", "https://accounts.google.com"])
def test_les_deux_emetteurs_legitimes_acceptes(monkeypatch, emetteur):
    brancher(monkeypatch, {**CHARGE_VALIDE, "iss": emetteur})

    assert verifier_jeton("un-jeton").sub == "112233445566778899"
