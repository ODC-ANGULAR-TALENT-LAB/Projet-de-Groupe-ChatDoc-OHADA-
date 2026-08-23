"""Le secret de session doit etre fort en production, ou rien ne demarre.

CE QUE CETTE GARDE PROTEGE. « a_changer_imperativement » est ecrit dans
config.py, donc lisible par quiconque ouvre le depot. Deploye tel quel,
n'importe qui peut forger un jeton de session pour n'importe quel compte,
administration comprise — et TOUT le reste tombe avec : mot de passe,
limitation des tentatives, controle des roles sont contournes d'un seul
coup.

PyJWT signale par ailleurs qu'une cle HMAC de moins de 32 octets est
insuffisante pour SHA-256 (RFC 7518 §3.2). Le defaut du depot en fait 24.
"""

import pytest

from app.main import LONGUEUR_SECRET_MINIMALE, SECRET_PAR_DEFAUT, _verifier_secret_jwt
from app.config import parametres


@pytest.fixture
def en_production(monkeypatch):
    monkeypatch.setattr(parametres, "production", True, raising=False)


@pytest.fixture
def en_developpement(monkeypatch):
    monkeypatch.setattr(parametres, "production", False, raising=False)


def test_le_secret_du_depot_arrete_le_demarrage(en_production, monkeypatch):
    monkeypatch.setattr(parametres, "jwt_secret", SECRET_PAR_DEFAUT, raising=False)
    with pytest.raises(RuntimeError, match="valeur d'exemple"):
        _verifier_secret_jwt()


def test_un_secret_trop_court_arrete_le_demarrage(en_production, monkeypatch):
    monkeypatch.setattr(parametres, "jwt_secret", "x" * 20, raising=False)
    with pytest.raises(RuntimeError, match="octets"):
        _verifier_secret_jwt()


def test_la_limite_est_bien_a_trente_deux(en_production, monkeypatch):
    """Juste en dessous refuse, juste au niveau passe."""
    monkeypatch.setattr(
        parametres, "jwt_secret", "x" * (LONGUEUR_SECRET_MINIMALE - 1), raising=False
    )
    with pytest.raises(RuntimeError):
        _verifier_secret_jwt()

    monkeypatch.setattr(
        parametres, "jwt_secret", "x" * LONGUEUR_SECRET_MINIMALE, raising=False
    )
    _verifier_secret_jwt()


def test_un_secret_correct_laisse_demarrer(en_production, monkeypatch):
    monkeypatch.setattr(parametres, "jwt_secret", "y" * 48, raising=False)
    _verifier_secret_jwt()


def test_le_developpement_n_est_pas_entrave(en_developpement, monkeypatch):
    """IMPOSER UN SECRET FORT POUR LANCER LES TESTS NE PROTEGERAIT RIEN.

    Cela ferait seulement perdre du temps a chaque personne qui clone le
    depot, et pousserait a contourner la garde plutot qu'a la respecter
    la ou elle compte.
    """
    monkeypatch.setattr(parametres, "jwt_secret", SECRET_PAR_DEFAUT, raising=False)
    _verifier_secret_jwt()


def test_les_espaces_ne_font_pas_illusion(en_production, monkeypatch):
    """Un secret rempli d'espaces n'est pas un secret long."""
    monkeypatch.setattr(parametres, "jwt_secret", "  court  ", raising=False)
    with pytest.raises(RuntimeError):
        _verifier_secret_jwt()
