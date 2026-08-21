"""Registre des signalements, vu par l'administration.

LE REGISTRE DES INCIDENTS EST UN DISPOSITIF DE PROTECTION (§16 ter), au
meme titre que les conditions d'utilisation : il demontre la diligence
de l'editeur en cas de litige. Il n'a de valeur que s'il est TENU — et
encore faut-il pouvoir le lire. Une route permettait d'y ecrire, aucune
de le consulter : le registre existait sans etre lisible.

CE QUI EST VERIFIE EN PRIORITE ICI : qu'il ne puisse pas etre vide de sa
substance. Deux facons de le vider, chacune avec son test :

  1. clore un signalement sans dire ce qui a ete fait — « traite » ne
     dit ni ce qui a ete constate, ni ce qui a ete corrige ;
  2. supprimer le compte de celui qui a signale. Un registre qu'un
     compte supprime peut effacer ne prouve rien le jour ou il faudrait
     s'en servir.
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


def _compte(email: str, role: str = "utilisateur") -> int:
    with FabriqueSession() as session:
        session.execute(text("DELETE FROM utilisateur WHERE email = :e"), {"e": email})
        identifiant = session.execute(
            text(
                "INSERT INTO utilisateur (email, mot_de_passe_hash, role) "
                "VALUES (:e, :h, :r) RETURNING id"
            ),
            {"e": email, "h": hacher("MotDePasse2026!"), "r": role},
        ).scalar()
        session.commit()
    return identifiant


def _effacer(email: str) -> None:
    with FabriqueSession() as session:
        session.execute(text("DELETE FROM utilisateur WHERE email = :e"), {"e": email})
        session.commit()


def _signaler(utilisateur_id: int, motif: str = "article_perime") -> int:
    """Fabrique un echange complet et son signalement.

    Un signalement isole ne suffit pas : la route joint la question et
    la reponse mises en cause, et c'est precisement ce que les tests
    doivent verifier.
    """
    with FabriqueSession() as session:
        conversation = session.execute(
            text(
                "INSERT INTO conversation (utilisateur_id, titre) "
                "VALUES (:u, 'Essai registre') RETURNING id"
            ),
            {"u": utilisateur_id},
        ).scalar()
        session.execute(
            text(
                "INSERT INTO message (conversation_id, role, contenu) "
                "VALUES (:c, 'user', 'Quel est le capital minimum d''une SARL ?')"
            ),
            {"c": conversation},
        )
        message = session.execute(
            text(
                "INSERT INTO message (conversation_id, role, contenu) "
                "VALUES (:c, 'assistant', 'Le capital minimum est de 1 000 000 FCFA.') "
                "RETURNING id"
            ),
            {"c": conversation},
        ).scalar()
        signalement = session.execute(
            text(
                "INSERT INTO signalement (message_id, utilisateur_id, motif, commentaire) "
                "VALUES (:m, :u, :mo, 'Ce montant a changé en 2014.') RETURNING id"
            ),
            {"m": message, "u": utilisateur_id, "mo": motif},
        ).scalar()
        session.commit()
    return signalement


@pytest.fixture
def patron():
    email = "essai-signal-admin@chatdocs-ohada.cm"
    identifiant = _compte(email, role="admin")
    yield {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    _effacer(email)


@pytest.fixture
def plaignant():
    email = "essai-signal-client@chatdocs-ohada.cm"
    identifiant = _compte(email)
    yield identifiant, email, {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    _effacer(email)


# ---------------------------------------------------------------------
# Le registre est lisible, et seulement par l'administration
# ---------------------------------------------------------------------


def test_le_registre_porte_la_question_et_la_reponse_contestee(
    client, patron, plaignant
):
    """TRANCHER SUPPOSE DE RELIRE L'ECHANGE.

    La table `message` stocke un tour par ligne : le signalement vise la
    reponse, et la question est le tour utilisateur qui la precede. Les
    joindre ici evite d'aller les chercher ailleurs — ce qui
    decouragerait de le faire.
    """
    identifiant, _, _ = plaignant
    signalement = _signaler(identifiant)

    lignes = client.get("/admin/signalements", headers=patron).json()
    mien = next(s for s in lignes if s["id"] == signalement)

    assert "SARL" in mien["question"]
    assert "1 000 000" in mien["reponse"]
    assert mien["motif"] == "article_perime"
    assert mien["statut"] == "ouvert"


def test_un_utilisateur_ordinaire_ne_lit_pas_le_registre(client, plaignant):
    """Il contient les questions et les reponses d'autres comptes."""
    _, _, entete = plaignant

    assert client.get("/admin/signalements", headers=entete).status_code == 403


def test_les_signalements_ouverts_viennent_en_premier(client, patron, plaignant):
    """L'ordre n'est pas cosmetique : ce qui attend un examen doit se
    voir sans faire defiler."""
    identifiant, _, _ = plaignant
    ouvert = _signaler(identifiant)
    clos = _signaler(identifiant, motif="hors_sujet")
    client.post(
        f"/admin/signalements/{clos}/traiter",
        json={"statut": "ecarte", "correction": "Hors sujet, sans suite."},
        headers=patron,
    )

    lignes = client.get("/admin/signalements", headers=patron).json()
    positions = {s["id"]: i for i, s in enumerate(lignes)}

    assert positions[ouvert] < positions[clos]


# ---------------------------------------------------------------------
# On ne clot pas sans dire ce qui a ete fait
# ---------------------------------------------------------------------


def test_clore_sans_correction_est_refuse(client, patron, plaignant):
    """LE TEST CENTRAL.

    « Traite » seul ne dit ni ce qui a ete constate, ni ce qui a ete
    corrige : le registre perdrait sa valeur probante le jour ou il
    faudrait s'en servir.
    """
    identifiant, _, _ = plaignant
    signalement = _signaler(identifiant)

    reponse = client.post(
        f"/admin/signalements/{signalement}/traiter",
        json={"statut": "traite", "correction": ""},
        headers=patron,
    )

    assert reponse.status_code == 422


@pytest.mark.parametrize("statut", ["corrige", "infonde", "doublon", "clos"])
def test_un_statut_hors_contrainte_est_refuse(client, patron, plaignant, statut):
    """LA CONTRAINTE SQL EST LA SOURCE DE VERITE.

    `signalement_statut_connu` n'accepte que « ouvert », « traite » et
    « ecarte ». En inventer d'autres cote API ferait echouer l'ecriture
    en 500 plutot qu'en refus lisible.
    """
    identifiant, _, _ = plaignant
    signalement = _signaler(identifiant)

    reponse = client.post(
        f"/admin/signalements/{signalement}/traiter",
        json={"statut": statut, "correction": "motif suffisant"},
        headers=patron,
    )

    assert reponse.status_code == 422


def test_la_cloture_consigne_ce_qui_a_ete_fait(client, patron, plaignant):
    identifiant, _, _ = plaignant
    signalement = _signaler(identifiant)

    reponse = client.post(
        f"/admin/signalements/{signalement}/traiter",
        json={
            "statut": "traite",
            "correction": "Article 311 AUSCGIE rechargé : capital libre depuis 2014.",
        },
        headers=patron,
    )

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["statut"] == "traite"
    assert "2014" in corps["correction"]
    assert corps["traite_le"] is not None


def test_un_signalement_deja_traite_ne_se_reclot_pas(client, patron, plaignant):
    """Sinon un rechargement de page ecraserait la correction consignee."""
    identifiant, _, _ = plaignant
    signalement = _signaler(identifiant)
    client.post(
        f"/admin/signalements/{signalement}/traiter",
        json={"statut": "traite", "correction": "Corpus corrigé."},
        headers=patron,
    )

    seconde = client.post(
        f"/admin/signalements/{signalement}/traiter",
        json={"statut": "ecarte", "correction": "Finalement non."},
        headers=patron,
    )

    assert seconde.status_code == 409


# ---------------------------------------------------------------------
# Le registre survit a la suppression de son auteur
# ---------------------------------------------------------------------


def test_supprimer_le_plaignant_ne_vide_pas_le_registre(client, patron, plaignant):
    """LA SECONDE FACON DE VIDER LE REGISTRE, ET LA PLUS INSIDIEUSE.

    Si supprimer un compte emportait ses signalements, il suffirait de
    supprimer un compte pour effacer ce qu'il avait conteste. La
    contrainte est posee en base — ON DELETE SET NULL — et non dans le
    code : elle vaut quelle que soit la voie de suppression.

    L'auteur est anonymise, le contenu reste.
    """
    identifiant, _, _ = plaignant
    signalement = _signaler(identifiant)

    assert (
        client.delete(f"/admin/utilisateurs/{identifiant}", headers=patron).status_code
        == 204
    )

    lignes = client.get("/admin/signalements", headers=patron).json()
    survivant = next((s for s in lignes if s["id"] == signalement), None)

    assert survivant is not None, "le signalement a disparu avec son auteur"
    assert survivant["email"] is None, "l'auteur devrait être anonymisé"
    assert survivant["motif"] == "article_perime"
