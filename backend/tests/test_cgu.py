"""Acceptation des conditions générales d'utilisation.

CE QUI EST VÉRIFIÉ ICI n'est pas la case à cocher — elle vit dans le
navigateur et s'y contourne avec deux lignes de console. C'est le
**refus côté serveur**, seul endroit où l'acceptation peut réellement
être exigée.

Et l'enregistrement de ce qui a été accepté : « a accepté » ne prouve
rien le jour où il faudrait le prouver. Accepté quand, et accepté quoi ?
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import parametres
from app.db import FabriqueSession
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def email() -> str:
    """Compte jetable, supprimé même si le test échoue."""
    adresse = "essai-cgu@chatdocs-ohada.cm"
    _effacer(adresse)
    yield adresse
    _effacer(adresse)


def _effacer(adresse: str) -> None:
    with FabriqueSession() as session:
        session.execute(
            text("DELETE FROM utilisateur WHERE email = :e"), {"e": adresse}
        )
        session.commit()


MDP = "EssaiCgu2026!"


def test_l_inscription_est_refusee_sans_acceptation(client, email):
    """LE TEST CENTRAL DE CE FICHIER.

    Une case décochée dans le formulaire n'engage rien : le client peut
    toujours envoyer la requête à la main. Le serveur doit refuser.
    """
    reponse = client.post(
        "/auth/inscription",
        json={"email": email, "mot_de_passe": MDP, "cgu_acceptees": False},
    )

    assert reponse.status_code == 422
    assert "conditions" in reponse.json()["detail"].lower()


def test_un_champ_omis_vaut_un_refus(client, email):
    """Le serveur ne consent pas à la place de l'utilisateur.

    Sans valeur par défaut à `True`, un client qui oublie le champ se
    voit refuser l'inscription — c'est le comportement voulu.
    """
    reponse = client.post(
        "/auth/inscription", json={"email": email, "mot_de_passe": MDP}
    )

    assert reponse.status_code == 422


def test_l_acceptation_enregistre_la_version_et_la_date(client, email):
    """« A accepté » ne suffit pas : accepté QUAND, et accepté QUOI ?

    Les conditions changent ; celui qui a coché sous une version n'a
    pas accepté la suivante.
    """
    reponse = client.post(
        "/auth/inscription",
        json={"email": email, "mot_de_passe": MDP, "cgu_acceptees": True},
    )
    assert reponse.status_code == 201

    with FabriqueSession() as session:
        version, accepte_le = session.execute(
            text(
                "SELECT cgu_version, cgu_acceptees_le FROM utilisateur "
                "WHERE email = :e"
            ),
            {"e": email},
        ).one()

    assert version == parametres.version_cgu
    assert accepte_le is not None


def test_la_connexion_ne_redemande_pas_l_acceptation(client, email):
    """On accepte une fois, à l'inscription — pas à chaque connexion.

    Redemander à chaque fois ferait cocher sans lire, ce qui vide la
    case de son sens.
    """
    client.post(
        "/auth/inscription",
        json={"email": email, "mot_de_passe": MDP, "cgu_acceptees": True},
    )

    reponse = client.post(
        "/auth/connexion", json={"email": email, "mot_de_passe": MDP}
    )

    assert reponse.status_code == 200
