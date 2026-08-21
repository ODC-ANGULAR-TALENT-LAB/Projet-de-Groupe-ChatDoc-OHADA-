"""Suspension et suppression d'un compte.

CE QUI EST VERIFIE EN PRIORITE ICI : qu'on ne puisse pas **fermer la
porte a clef de l'interieur**. Retirer le dernier administrateur —
en le retrogradant, en le suspendant ou en le supprimant — rendrait la
console definitivement inaccessible : aucune route ne fabrique un
administrateur, et le script qui le fait suppose un acces au serveur.

Et qu'une suppression n'efface pas ce qui doit lui survivre : le
registre des signalements, et le nom du juriste inscrit dans la table
de provenance publiee.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import FabriqueSession
from app.main import app
from app.services.securite import creer_jeton, hacher


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _compte(email: str, role: str = "utilisateur", mdp: str = "MotDePasse2026!") -> int:
    with FabriqueSession() as session:
        session.execute(text("DELETE FROM utilisateur WHERE email = :e"), {"e": email})
        identifiant = session.execute(
            text(
                "INSERT INTO utilisateur (email, mot_de_passe_hash, role) "
                "VALUES (:e, :h, :r) RETURNING id"
            ),
            {"e": email, "h": hacher(mdp), "r": role},
        ).scalar()
        session.commit()
    return identifiant


def _effacer(email: str) -> None:
    with FabriqueSession() as session:
        session.execute(text("DELETE FROM utilisateur WHERE email = :e"), {"e": email})
        session.commit()


@pytest.fixture
def patron():
    """Un administrateur SUPPLEMENTAIRE.

    Il en existe deja un dans la base de developpement ; ce second
    compte permet d'eprouver la suspension d'un administrateur sans se
    heurter a la protection du dernier.
    """
    email = "essai-admin-second@chatdocs-ohada.cm"
    identifiant = _compte(email, role="admin")
    yield identifiant, {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    _effacer(email)


@pytest.fixture
def cible():
    email = "essai-cible@chatdocs-ohada.cm"
    identifiant = _compte(email)
    yield identifiant, email, {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    _effacer(email)


# ---------------------------------------------------------------------
# On ne ferme pas la porte a clef de l'interieur
# ---------------------------------------------------------------------


def test_un_administrateur_ne_se_suspend_pas_lui_meme(client, patron):
    """LE TEST CENTRAL.

    Se suspendre soi-meme rendrait la console inaccessible a celui qui
    vient de le faire, sans qu'aucun autre chemin ne permette d'y
    revenir.
    """
    identifiant, entete = patron

    reponse = client.post(
        f"/admin/utilisateurs/{identifiant}/suspendre",
        json={"motif": "essai"},
        headers=entete,
    )

    assert reponse.status_code == 409


def test_un_administrateur_ne_se_supprime_pas_lui_meme(client, patron):
    identifiant, entete = patron

    reponse = client.delete(f"/admin/utilisateurs/{identifiant}", headers=entete)

    assert reponse.status_code == 409


def test_une_suspension_sans_motif_est_refusee(client, patron, cible):
    """Une suspension sans raison rend toute reactivation arbitraire."""
    _, entete = patron
    identifiant, _, _ = cible

    reponse = client.post(
        f"/admin/utilisateurs/{identifiant}/suspendre",
        json={"motif": ""},
        headers=entete,
    )

    assert reponse.status_code == 422


# ---------------------------------------------------------------------
# Suspendre ferme les deux portes
# ---------------------------------------------------------------------


def test_un_compte_suspendu_ne_se_connecte_plus(client, patron, cible):
    """LA PORTE D'ENTREE.

    Sans ce controle, la connexion reussissait, le jeton etait emis, et
    chaque appel suivant repondait 403 — ce qui ressemble a une panne
    plutot qu'a une decision.
    """
    _, entete = patron
    identifiant, email, _ = cible
    client.post(
        f"/admin/utilisateurs/{identifiant}/suspendre",
        json={"motif": "Usage abusif."},
        headers=entete,
    )

    reponse = client.post(
        "/auth/connexion", json={"email": email, "mot_de_passe": "MotDePasse2026!"}
    )

    assert reponse.status_code == 403
    assert "suspendu" in reponse.json()["detail"].lower()


def test_une_session_deja_ouverte_se_ferme_aussi(client, patron, cible):
    """LA SECONDE PORTE.

    Ne fermer que l'entree laisserait la session ouverte avant la
    suspension fonctionner jusqu'a son expiration, soit douze heures.
    """
    _, entete = patron
    identifiant, _, entete_cible = cible
    assert client.get("/moi/quota", headers=entete_cible).status_code == 200

    client.post(
        f"/admin/utilisateurs/{identifiant}/suspendre",
        json={"motif": "Usage abusif."},
        headers=entete,
    )

    assert client.get("/moi/quota", headers=entete_cible).status_code == 403


def test_la_reactivation_rouvre_les_deux(client, patron, cible):
    _, entete = patron
    identifiant, email, entete_cible = cible
    client.post(
        f"/admin/utilisateurs/{identifiant}/suspendre",
        json={"motif": "Essai."},
        headers=entete,
    )

    client.post(f"/admin/utilisateurs/{identifiant}/reactiver", headers=entete)

    assert client.get("/moi/quota", headers=entete_cible).status_code == 200
    assert (
        client.post(
            "/auth/connexion",
            json={"email": email, "mot_de_passe": "MotDePasse2026!"},
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------
# Ce qu'une suppression n'efface pas
# ---------------------------------------------------------------------


def test_un_compte_ordinaire_se_supprime(client, patron, cible):
    _, entete = patron
    identifiant, email, _ = cible

    assert client.delete(f"/admin/utilisateurs/{identifiant}", headers=entete).status_code == 204

    with FabriqueSession() as session:
        reste = session.execute(
            text("SELECT 1 FROM utilisateur WHERE email = :e"), {"e": email}
        ).first()
    assert reste is None


def test_un_compte_ayant_valide_un_texte_ne_se_supprime_pas(client, patron):
    """LE NOM DU JURISTE FIGURE DANS LA TABLE DE PROVENANCE PUBLIEE.

    C'est la chaine de responsabilite qui permet de repondre d'une
    citation contestee. Un tel compte se suspend, il ne s'efface pas.
    La contrainte est aussi posee en base (ON DELETE RESTRICT) : le
    controle applicatif donne un message clair, la contrainte garantit
    qu'aucune autre voie ne la contourne.
    """
    _, entete = patron

    with FabriqueSession() as session:
        deposant = session.execute(
            text("SELECT depose_par FROM depot WHERE depose_par IS NOT NULL LIMIT 1")
        ).scalar()

    if deposant is None:
        pytest.skip("Aucun dépôt en base : la règle n'est pas éprouvable ici.")

    reponse = client.delete(f"/admin/utilisateurs/{deposant}", headers=entete)

    assert reponse.status_code == 409
    assert "corpus" in reponse.json()["detail"]


def test_un_utilisateur_ordinaire_ne_suspend_ni_ne_supprime(client, cible):
    """Ces gestes sont reserves a l'administration."""
    identifiant, _, entete = cible

    assert (
        client.post(
            f"/admin/utilisateurs/{identifiant}/suspendre",
            json={"motif": "essai"},
            headers=entete,
        ).status_code
        == 403
    )
    assert client.delete(f"/admin/utilisateurs/{identifiant}", headers=entete).status_code == 403
