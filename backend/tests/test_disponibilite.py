"""Les deux sondes de disponibilite : /vie et /sante.

POURQUOI DEUX SONDES. L'API a ete hors service trois semaines et demie
(du 20 septembre au 14 octobre 2026) sans que personne ne le sache : la
base gratuite de Render avait expire, et la seule sonde, /sante,
repondait... 200 tant que le processus tournait, en ecrivant « base
indisponible » dans un corps que rien ne lisait.

  /vie   — le processus repond. Aucune requete en base : c'est la sonde
           appelee toutes les cinq minutes pour empecher l'API de
           s'endormir, et la base (Neon) doit, elle, pouvoir dormir. Une
           sonde frequente qui interrogerait la base la tiendrait
           eveillee en permanence et epuiserait son quota de calcul
           gratuit avant la fin du mois.
  /sante — le service fonctionne vraiment, base comprise. Elle repond
           503 quand la base manque, pour qu'une sonde externe declenche
           une alerte au lieu de voir un « 200 » rassurant.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as principal


class MoteurEnPanne:
    """Remplace le moteur SQLAlchemy : toute connexion echoue, et l'on
    compte les tentatives pour verifier qu'une sonde n'en fait aucune."""

    def __init__(self) -> None:
        self.tentatives = 0

    def connect(self):
        self.tentatives += 1
        raise ConnectionError("base injoignable")


@pytest.fixture
def moteur_en_panne(monkeypatch) -> MoteurEnPanne:
    moteur = MoteurEnPanne()
    monkeypatch.setattr(principal, "moteur", moteur)
    return moteur


@pytest.fixture
def client() -> TestClient:
    return TestClient(principal.app)


def test_vie_repond_sans_toucher_a_la_base(client, moteur_en_panne):
    reponse = client.get("/vie")

    assert reponse.status_code == 200
    assert moteur_en_panne.tentatives == 0


def test_sante_signale_une_base_indisponible_par_un_503(client, moteur_en_panne):
    reponse = client.get("/sante")

    assert reponse.status_code == 503
    assert reponse.json()["base"] == "indisponible"


def test_vie_et_sante_sont_publiques(client, moteur_en_panne):
    """Une sonde externe n'a pas de jeton : exiger une authentification
    ici rendrait la surveillance impossible."""
    assert client.get("/vie").status_code != 401
    assert client.get("/sante").status_code != 401
