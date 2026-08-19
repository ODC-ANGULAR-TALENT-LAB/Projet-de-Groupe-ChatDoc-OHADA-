"""Avis des utilisateurs sur l'application.

CE QUI EST VÉRIFIÉ EN PRIORITÉ ICI, ce n'est pas qu'un avis s'enregistre
— c'est que **la moyenne ne puisse pas être faussée**.

Deux voies la fausseraient : une note hors bornes, et plusieurs avis
déposés par la même personne. La première est fermée deux fois, dans
l'API et par une contrainte SQL ; la seconde par une contrainte
d'unicité qui transforme le second dépôt en révision du premier.

Et que les avis restent privés : ils portent le nom de leur auteur, et
rien ne doit les exposer aux autres utilisateurs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import FabriqueSession
from app.main import app
from app.services.securite import creer_jeton


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _compte(email: str, role: str = "utilisateur") -> int:
    """Compte jetable, recréé à neuf pour chaque test."""
    with FabriqueSession() as session:
        session.execute(text("DELETE FROM utilisateur WHERE email = :e"), {"e": email})
        identifiant = session.execute(
            text(
                "INSERT INTO utilisateur (email, mot_de_passe_hash, role) "
                "VALUES (:e, 'x', :r) RETURNING id"
            ),
            {"e": email, "r": role},
        ).scalar()
        session.commit()
    return identifiant


def _effacer(email: str) -> None:
    with FabriqueSession() as session:
        session.execute(text("DELETE FROM utilisateur WHERE email = :e"), {"e": email})
        session.commit()


@pytest.fixture
def lecteur():
    email = "essai-avis@chatdocs-ohada.cm"
    identifiant = _compte(email)
    yield {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    _effacer(email)


@pytest.fixture
def patron():
    email = "essai-avis-admin@chatdocs-ohada.cm"
    identifiant = _compte(email, role="admin")
    yield {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    _effacer(email)


# ---------------------------------------------------------------------
# La moyenne ne peut pas être faussée
# ---------------------------------------------------------------------


@pytest.mark.parametrize("note", [0, -1, 6, 9, 100])
def test_une_note_hors_bornes_est_refusee(client, lecteur, note):
    """LE TEST CENTRAL DE CE FICHIER.

    Une note hors de l'échelle rendrait toute moyenne fausse sans que
    rien ne le signale — et une moyenne fausse est pire qu'absente,
    parce qu'on la croit.
    """
    reponse = client.put("/moi/avis", json={"note": note}, headers=lecteur)

    assert reponse.status_code == 422


def test_un_deuxieme_avis_revise_le_premier_au_lieu_de_s_ajouter(client, lecteur):
    """Sinon, celui qui revient trois fois pèserait trois fois."""
    client.put("/moi/avis", json={"note": 2}, headers=lecteur)
    client.put("/moi/avis", json={"note": 5}, headers=lecteur)

    mien = client.get("/moi/avis", headers=lecteur).json()

    assert mien["note"] == 5
    # La date de création ne bouge pas ; seule la révision est datée.
    assert mien["modifie_le"] is not None


def test_la_moyenne_est_toujours_accompagnee_du_nombre(client, lecteur, patron):
    """4,0 sur deux avis et 4,0 sur deux cents ne se pilotent pas pareil.

    Servir la moyenne seule inviterait à conclure sur trois avis.
    """
    client.put("/moi/avis", json={"note": 4}, headers=lecteur)

    synthese = client.get("/admin/avis", headers=patron).json()

    assert synthese["moyenne"] is not None
    assert synthese["nombre"] >= 1
    assert sum(synthese["repartition"].values()) == synthese["nombre"]


# ---------------------------------------------------------------------
# Dépôt, révision, retrait
# ---------------------------------------------------------------------


def test_sans_avis_la_route_rend_null_et_non_une_erreur(client, lecteur):
    """N'avoir pas encore donné son avis est l'état normal.

    Un 404 obligerait l'interface à traiter comme une panne ce qui est
    le cas de figure le plus courant.
    """
    reponse = client.get("/moi/avis", headers=lecteur)

    assert reponse.status_code == 200
    assert reponse.json() is None


def test_la_note_suffit_le_commentaire_est_facultatif(client, lecteur):
    """Exiger un texte ferait renoncer ceux qui n'ont qu'une impression."""
    reponse = client.put("/moi/avis", json={"note": 3}, headers=lecteur)

    assert reponse.status_code == 200
    assert reponse.json()["commentaire"] is None


def test_un_commentaire_vide_vaut_une_absence_de_commentaire(client, lecteur):
    """Sinon la base se remplirait de chaînes d'espaces."""
    reponse = client.put(
        "/moi/avis", json={"note": 3, "commentaire": "   "}, headers=lecteur
    )

    assert reponse.json()["commentaire"] is None


def test_un_avis_peut_etre_retire(client, lecteur):
    """Un commentaire écrit sous le coup de l'agacement ne doit pas
    rester attaché au compte pour toujours."""
    client.put("/moi/avis", json={"note": 1, "commentaire": "Rien ne va."}, headers=lecteur)

    assert client.delete("/moi/avis", headers=lecteur).status_code == 204
    assert client.get("/moi/avis", headers=lecteur).json() is None


# ---------------------------------------------------------------------
# Les avis restent privés
# ---------------------------------------------------------------------


def test_un_utilisateur_ordinaire_ne_lit_pas_les_avis_des_autres(client, lecteur):
    """Les avis portent le nom de leur auteur.

    Les exposer dirait qui utilise le produit — ce que personne n'a
    accepté en déposant son avis.
    """
    assert client.get("/admin/avis", headers=lecteur).status_code == 403


def test_sans_jeton_on_ne_depose_ni_ne_lit_d_avis(client):
    assert client.get("/moi/avis").status_code == 401
    assert client.put("/moi/avis", json={"note": 5}).status_code == 401


def test_l_administration_voit_l_auteur_de_chaque_avis(client, lecteur, patron):
    """Répondre à un avis suppose de savoir de qui il vient."""
    client.put("/moi/avis", json={"note": 4}, headers=lecteur)

    synthese = client.get("/admin/avis", headers=patron).json()
    depose = [a for a in synthese["avis"] if a["email"] == "essai-avis@chatdocs-ohada.cm"]

    assert len(depose) == 1
    assert depose[0]["note"] == 4
