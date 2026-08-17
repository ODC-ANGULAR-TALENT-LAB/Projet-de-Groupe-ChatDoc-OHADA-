"""Tests du hachage et des jetons de session (phase G)."""

from __future__ import annotations

import datetime

import pytest
from jose import jwt

from app.config import parametres
from app.services.securite import ALGORITHME, creer_jeton, hacher, lire_jeton, verifier


def test_le_mot_de_passe_n_est_pas_stocke_en_clair():
    empreinte = hacher("un mot de passe")

    assert "un mot de passe" not in empreinte
    assert empreinte.startswith("$2")


def test_deux_hachages_different():
    """Le sel rend deux empreintes du meme mot de passe distinctes."""
    assert hacher("identique") != hacher("identique")


def test_verification_du_bon_mot_de_passe():
    assert verifier("correct", hacher("correct"))


def test_verification_du_mauvais_mot_de_passe():
    assert not verifier("faux", hacher("correct"))


def test_le_jeton_porte_l_identifiant():
    assert lire_jeton(creer_jeton(42)) == 42


def test_jeton_signe_avec_un_autre_secret_rejete():
    faux = jwt.encode({"sub": "42"}, "un autre secret", algorithm=ALGORITHME)

    assert lire_jeton(faux) is None


def test_jeton_expire_rejete():
    perime = jwt.encode(
        {
            "sub": "42",
            "exp": datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=1),
        },
        parametres.jwt_secret,
        algorithm=ALGORITHME,
    )

    assert lire_jeton(perime) is None


@pytest.mark.parametrize("jeton", ["", "n'importe quoi", "a.b.c"])
def test_jeton_malforme_rejete(jeton):
    assert lire_jeton(jeton) is None
