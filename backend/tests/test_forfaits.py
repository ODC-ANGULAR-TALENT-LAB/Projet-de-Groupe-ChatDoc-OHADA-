"""Forfaits, credits d'usage, et abonnements.

CE QUI EST VERIFIE EN PRIORITE ICI, ce n'est pas qu'un forfait
s'affiche — c'est que **le produit ne puisse pas se vendre a perte**,
et qu'on **ne puisse pas s'offrir des credits soi-meme**.

Le premier point est une contrainte economique qui, sans test, ne se
verrait qu'a la fin du mois sur le relevé bancaire : rien dans le code
ne signale qu'un forfait a 90 credits devient perdant si le cout de la
question double. Le second est une contrainte de securite ordinaire,
mais dont l'oubli se paierait directement en argent.
"""

from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import parametres
from app.db import FabriqueSession
from app.main import app
from app.services.forfaits import (
    FORFAITS,
    MARGE_MINIMALE,
    credits_du_plan,
    forfait,
)
from app.services.securite import creer_jeton


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _compte(email: str, role: str = "utilisateur") -> int:
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
def abonne():
    email = "essai-forfait@chatdocs-ohada.cm"
    identifiant = _compte(email)
    yield identifiant, {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    _effacer(email)


@pytest.fixture
def patron():
    email = "essai-forfait-admin@chatdocs-ohada.cm"
    identifiant = _compte(email, role="admin")
    yield {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    _effacer(email)


# ---------------------------------------------------------------------
# Le produit ne peut pas se vendre a perte
# ---------------------------------------------------------------------


@pytest.mark.parametrize("f", [f for f in FORFAITS if f.prix_fcfa > 0], ids=lambda f: f.code)
def test_chaque_forfait_payant_degage_la_marge_minimale(f):
    """LE TEST CENTRAL DE CE FICHIER.

    Il ne verifie pas un comportement mais une CONTRAINTE ECONOMIQUE :
    ajouter des credits sans revoir le prix doit casser la suite de
    tests, pas le compte en banque.

    La marge est calculee sur la consommation TOTALE des credits, pas
    moyenne : un forfait doit rester rentable face a l'utilisateur qui
    epuise ce qu'il a paye, sinon la rentabilite ne tient que parce que
    les clients n'utilisent pas leur forfait.
    """
    assert f.marge is not None
    assert f.marge >= MARGE_MINIMALE, (
        f"{f.libelle} : {f.marge:.1%} de marge, en dessous du plancher de "
        f"{MARGE_MINIMALE:.0%}. Baissez les credits ou montez le prix."
    )


def test_la_marge_reste_dans_la_fourchette_visee():
    """Entre 50 et 60 %.

    Le plafond compte autant que le plancher : au-dela, le forfait
    devient cher pour ce qu'il donne, et un catalogue qu'on n'achete
    pas ne rapporte rien non plus.
    """
    for f in FORFAITS:
        if f.prix_fcfa == 0:
            continue
        assert 0.50 <= f.marge <= 0.60, f"{f.libelle} : {f.marge:.1%}"


def test_le_forfait_gratuit_n_a_pas_de_marge_a_calculer():
    """C'est un cout d'acquisition assume, pas une vente ratee.

    Calculer une marge de -100 % inviterait a « corriger » le gratuit.
    """
    assert forfait("gratuit").marge is None


def test_un_cout_double_ferait_echouer_le_plancher(monkeypatch):
    """Le garde-fou garde-t-il vraiment ?

    Un test qui passe toujours ne protege de rien. Celui-ci verifie que
    le seuil se declenche : si la facture du fournisseur doublait, les
    forfaits actuels deviendraient insoutenables et on doit le savoir.
    """
    monkeypatch.setattr(parametres, "cout_question_fcfa", parametres.cout_question_fcfa * 2)

    payants = [f for f in FORFAITS if f.prix_fcfa > 0]
    assert any(f.marge < MARGE_MINIMALE for f in payants)


# ---------------------------------------------------------------------
# On ne s'offre pas des credits soi-meme
# ---------------------------------------------------------------------


def test_demander_un_forfait_payant_n_ouvre_aucun_credit(client, abonne):
    """LE SECOND TEST CENTRAL.

    Deposer une demande ne doit rien changer au plan ni aux credits :
    sinon il suffirait d'appeler l'API pour s'abonner gratuitement.
    """
    _, entete = abonne

    reponse = client.post("/moi/abonnement", json={"forfait": "cabinet"}, headers=entete)

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["forfait"]["code"] == "gratuit"
    assert corps["credits_restants"] <= credits_du_plan("gratuit")
    assert corps["demande_en_attente"] == "cabinet"


def test_un_utilisateur_ordinaire_ne_valide_pas_sa_propre_demande(client, abonne):
    """Seule l'administration ouvre les credits."""
    identifiant, entete = abonne
    client.post("/moi/abonnement", json={"forfait": "essentiel"}, headers=entete)

    demande = _id_demande(identifiant)
    reponse = client.post(
        f"/admin/abonnements/{demande}/valider",
        json={"reference": "MOMO-123456"},
        headers=entete,
    )

    assert reponse.status_code == 403


def _id_demande(utilisateur_id: int) -> int:
    with FabriqueSession() as session:
        return session.execute(
            text(
                "SELECT id FROM demande_abonnement WHERE utilisateur_id = :uid "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"uid": utilisateur_id},
        ).scalar()


def test_la_validation_ouvre_les_credits_et_pose_une_echeance(client, abonne, patron):
    identifiant, entete = abonne
    client.post("/moi/abonnement", json={"forfait": "essentiel"}, headers=entete)

    valide = client.post(
        f"/admin/abonnements/{_id_demande(identifiant)}/valider",
        json={"reference": "MOMO-987654"},
        headers=patron,
    )
    assert valide.status_code == 200

    mien = client.get("/moi/abonnement", headers=entete).json()
    assert mien["forfait"]["code"] == "essentiel"
    assert mien["credits_restants"] == credits_du_plan("essentiel")
    assert mien["echeance"] is not None
    assert mien["demande_en_attente"] is None


def test_une_validation_sans_reference_de_paiement_est_refusee(client, abonne, patron):
    """Sans elle, un litige sur un abonnement ne se tranche pas."""
    identifiant, entete = abonne
    client.post("/moi/abonnement", json={"forfait": "essentiel"}, headers=entete)

    reponse = client.post(
        f"/admin/abonnements/{_id_demande(identifiant)}/valider",
        json={"reference": ""},
        headers=patron,
    )

    assert reponse.status_code == 422


def test_une_demande_deja_traitee_ne_se_valide_pas_deux_fois(client, abonne, patron):
    """Sinon un rechargement de page offrirait un mois de plus."""
    identifiant, entete = abonne
    client.post("/moi/abonnement", json={"forfait": "essentiel"}, headers=entete)
    demande = _id_demande(identifiant)

    client.post(
        f"/admin/abonnements/{demande}/valider",
        json={"reference": "MOMO-1"},
        headers=patron,
    )
    seconde = client.post(
        f"/admin/abonnements/{demande}/valider",
        json={"reference": "MOMO-2"},
        headers=patron,
    )

    assert seconde.status_code == 409


# ---------------------------------------------------------------------
# Echeance
# ---------------------------------------------------------------------


def test_un_abonnement_echu_retombe_sur_le_gratuit(client, abonne, patron):
    """Sans cela, un paiement unique ouvrirait le forfait pour toujours."""
    identifiant, entete = abonne
    client.post("/moi/abonnement", json={"forfait": "cabinet"}, headers=entete)
    client.post(
        f"/admin/abonnements/{_id_demande(identifiant)}/valider",
        json={"reference": "MOMO-ECHU"},
        headers=patron,
    )

    # On antidate l'echeance : l'abonnement est expire depuis hier.
    with FabriqueSession() as session:
        session.execute(
            text("UPDATE utilisateur SET plan_echeance = :hier WHERE id = :id"),
            {"hier": datetime.date.today() - datetime.timedelta(days=1), "id": identifiant},
        )
        session.commit()

    mien = client.get("/moi/abonnement", headers=entete).json()

    assert mien["forfait"]["code"] == "gratuit"
    assert mien["credits_restants"] == credits_du_plan("gratuit")


# ---------------------------------------------------------------------
# Changement de forfait
# ---------------------------------------------------------------------


def test_le_catalogue_est_lisible_sans_compte(client):
    """Le prix est ce qu'on veut connaitre AVANT de s'inscrire."""
    reponse = client.get("/forfaits")

    assert reponse.status_code == 200
    codes = [f["code"] for f in reponse.json()]
    assert codes == ["gratuit", "essentiel", "cabinet"]


def test_le_catalogue_ne_publie_jamais_la_marge(client):
    """C'est une donnee interne : la publier afficherait au client ce
    que le service gagne sur lui."""
    corps = client.get("/forfaits").text

    assert "marge" not in corps
    assert "cout" not in corps


def test_le_retour_au_gratuit_est_immediat(client, abonne, patron):
    """Faire attendre quelqu'un qui renonce serait le retenir de force."""
    identifiant, entete = abonne
    client.post("/moi/abonnement", json={"forfait": "essentiel"}, headers=entete)
    client.post(
        f"/admin/abonnements/{_id_demande(identifiant)}/valider",
        json={"reference": "MOMO-X"},
        headers=patron,
    )

    reponse = client.post("/moi/abonnement", json={"forfait": "gratuit"}, headers=entete)

    assert reponse.json()["forfait"]["code"] == "gratuit"
    assert reponse.json()["echeance"] is None


def test_renoncer_ne_recharge_pas_les_credits(client, abonne):
    """Sinon renoncer a un forfait deviendrait un moyen de se
    reapprovisionner."""
    identifiant, entete = abonne
    with FabriqueSession() as session:
        session.execute(
            text("UPDATE utilisateur SET quota_restant = 2 WHERE id = :id"),
            {"id": identifiant},
        )
        session.commit()

    reponse = client.post("/moi/abonnement", json={"forfait": "gratuit"}, headers=entete)

    assert reponse.status_code in (200, 409)
    if reponse.status_code == 200:
        assert reponse.json()["credits_restants"] == 2


def test_deux_demandes_en_attente_sont_refusees(client, abonne):
    """La seconde remplacerait la premiere sans qu'on sache laquelle honorer."""
    _, entete = abonne
    client.post("/moi/abonnement", json={"forfait": "essentiel"}, headers=entete)

    seconde = client.post("/moi/abonnement", json={"forfait": "cabinet"}, headers=entete)

    assert seconde.status_code == 409


def test_une_demande_peut_etre_annulee(client, abonne):
    """Quelqu'un qui se trompe de forfait ne doit pas rester bloque."""
    _, entete = abonne
    client.post("/moi/abonnement", json={"forfait": "cabinet"}, headers=entete)

    assert client.delete("/moi/abonnement/demande", headers=entete).status_code == 204
    assert client.get("/moi/abonnement", headers=entete).json()["demande_en_attente"] is None


def test_un_forfait_inconnu_est_refuse(client, abonne):
    _, entete = abonne

    assert client.post(
        "/moi/abonnement", json={"forfait": "platine"}, headers=entete
    ).status_code == 404
