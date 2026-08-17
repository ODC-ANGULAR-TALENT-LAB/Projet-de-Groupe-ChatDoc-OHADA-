"""Tests des en-tetes de securite HTTP (phase H).

HSTS est le piege : pose en developpement, il force le navigateur a
passer localhost en HTTPS, avec un cache que l'utilisateur ne sait pas
purger. Il ne doit apparaitre qu'en production.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import parametres
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_entetes_de_base_toujours_poses(client):
    reponse = client.get("/")

    assert reponse.headers["x-content-type-options"] == "nosniff"
    assert reponse.headers["x-frame-options"] == "DENY"
    assert reponse.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_hsts_absent_en_developpement(client, monkeypatch):
    monkeypatch.setattr(parametres, "production", False)

    assert "strict-transport-security" not in client.get("/").headers


def test_hsts_pose_en_production(client, monkeypatch):
    monkeypatch.setattr(parametres, "production", True)

    entete = client.get("/").headers["strict-transport-security"]

    assert "max-age=31536000" in entete
    assert "includeSubDomains" in entete


def test_diagnostic_masque_en_production(client, monkeypatch):
    """Le detail d'erreur expose la chaine de connexion : utile en
    developpement, a ne jamais publier."""
    monkeypatch.setattr(parametres, "production", True)
    monkeypatch.setattr(
        parametres, "database_url", "postgresql://x:y@hote-inexistant:5432/z"
    )

    etat = client.get("/sante").json()

    if etat["base"] == "indisponible":
        assert "detail" not in etat


def test_cors_refuse_une_origine_inconnue(client):
    reponse = client.get("/", headers={"Origin": "http://mechant.example"})

    assert "access-control-allow-origin" not in reponse.headers
