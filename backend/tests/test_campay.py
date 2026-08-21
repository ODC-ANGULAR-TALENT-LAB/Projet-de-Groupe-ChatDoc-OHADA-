"""Encaissement Mobile Money via CamPay.

AUCUN APPEL REEL N'EST FAIT ICI. CamPay est simule : lancer de vrais
paiements depuis une suite de tests debiterait des gens.

CE QUI EST VERIFIE EN PRIORITE, ce n'est pas qu'un paiement aboutisse —
c'est qu'on **ne puisse pas s'offrir un abonnement sans payer**. Trois
portes existent, et chacune a son test :

  1. le montant, qui ne doit jamais venir du navigateur ;
  2. le rappel (webhook), URL publique ou un faux « SUCCESSFUL »
     suffirait sans verification de signature ;
  3. la double activation, le rappel et la verification du navigateur
     pouvant arriver ensemble.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import text

from app.config import parametres
from app.db import FabriqueSession
from app.main import app
from app.services import campay
from app.services.forfaits import credits_du_plan, par_code
from app.services.securite import creer_jeton

CLE_WEBHOOK = "cle-de-test-du-webhook"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def campay_configure(monkeypatch):
    """CamPay joignable et signe, sans reseau."""
    monkeypatch.setattr(parametres, "campay_username", "essai")
    monkeypatch.setattr(parametres, "campay_password", "essai")
    monkeypatch.setattr(parametres, "campay_webhook_cle", CLE_WEBHOOK)
    campay.oublier_jeton()
    yield
    campay.oublier_jeton()


def _compte(email: str) -> int:
    with FabriqueSession() as session:
        session.execute(text("DELETE FROM utilisateur WHERE email = :e"), {"e": email})
        identifiant = session.execute(
            text(
                "INSERT INTO utilisateur (email, mot_de_passe_hash, role) "
                "VALUES (:e, 'x', 'utilisateur') RETURNING id"
            ),
            {"e": email},
        ).scalar()
        session.commit()
    return identifiant


@pytest.fixture
def abonne():
    email = "essai-campay@chatdocs-ohada.cm"
    identifiant = _compte(email)
    yield identifiant, {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    with FabriqueSession() as session:
        session.execute(text("DELETE FROM utilisateur WHERE email = :e"), {"e": email})
        session.commit()


@pytest.fixture
def collecte_simulee(monkeypatch):
    """Remplace l'appel reseau de la collecte, et retient ses arguments."""
    vues = {}

    def faux_collecter(montant, numero, description, reference_externe):
        vues.update(
            montant=montant,
            numero=numero,
            description=description,
            reference_externe=reference_externe,
        )
        return {
            "reference": "ref-campay-essai",
            "code_ussd": "*126#",
            "operateur": "MTN",
            "numero": campay.normaliser_numero(numero),
        }

    monkeypatch.setattr(campay, "collecter", faux_collecter)
    return vues


def _signature() -> str:
    return jwt.encode({"ref": "essai"}, CLE_WEBHOOK, algorithm="HS256")


def _reference(utilisateur_id: int) -> str | None:
    with FabriqueSession() as session:
        return session.execute(
            text(
                "SELECT campay_reference FROM demande_abonnement "
                "WHERE utilisateur_id = :uid ORDER BY id DESC LIMIT 1"
            ),
            {"uid": utilisateur_id},
        ).scalar()


# ---------------------------------------------------------------------
# Le montant ne vient jamais du navigateur
# ---------------------------------------------------------------------


def test_le_montant_est_lu_dans_le_catalogue(client, abonne, collecte_simulee):
    """LE PREMIER TEST CENTRAL.

    Le corps de la requete ne porte qu'un code de forfait et un numero.
    Si le montant pouvait venir du navigateur, chacun choisirait son
    prix.
    """
    _, entete = abonne

    client.post(
        "/moi/abonnement/payer",
        json={"forfait": "cabinet", "telephone": "699000000", "amount": 1},
        headers=entete,
    )

    assert collecte_simulee["montant"] == par_code()["cabinet"].prix_fcfa == 8000


def test_un_forfait_gratuit_ne_se_paie_pas(client, abonne, collecte_simulee):
    _, entete = abonne

    reponse = client.post(
        "/moi/abonnement/payer",
        json={"forfait": "gratuit", "telephone": "699000000"},
        headers=entete,
    )

    assert reponse.status_code == 404


# ---------------------------------------------------------------------
# Le rappel est traite comme hostile
# ---------------------------------------------------------------------


def test_un_rappel_sans_signature_valide_n_ouvre_rien(client, abonne, collecte_simulee):
    """LE SECOND TEST CENTRAL.

    L'URL de rappel est publique par nature. Sans verification de
    signature, il suffirait d'y poster un « SUCCESSFUL » pour s'offrir
    un abonnement.
    """
    identifiant, entete = abonne
    client.post(
        "/moi/abonnement/payer",
        json={"forfait": "essentiel", "telephone": "699000000"},
        headers=entete,
    )

    reponse = client.post(
        "/paiements/campay",
        json={
            "status": campay.REUSSI,
            "reference": _reference(identifiant),
            "signature": "jeton-forge",
        },
    )

    assert reponse.status_code == 401
    assert client.get("/moi/abonnement", headers=entete).json()["forfait"]["code"] == "gratuit"


def test_sans_cle_de_webhook_configuree_le_rappel_est_refuse(client, monkeypatch):
    """Accepter « en attendant » est la configuration qu'on oublie de
    refermer."""
    monkeypatch.setattr(parametres, "campay_webhook_cle", "")

    assert campay.signature_valide(_signature()) is False


def test_un_rappel_signe_ouvre_l_abonnement(client, abonne, collecte_simulee):
    identifiant, entete = abonne
    client.post(
        "/moi/abonnement/payer",
        json={"forfait": "essentiel", "telephone": "699000000"},
        headers=entete,
    )

    reponse = client.post(
        "/paiements/campay",
        json={
            "status": campay.REUSSI,
            "reference": _reference(identifiant),
            "operator_reference": "MTN-123",
            "signature": _signature(),
        },
    )

    assert reponse.status_code == 200
    mien = client.get("/moi/abonnement", headers=entete).json()
    assert mien["forfait"]["code"] == "essentiel"
    assert mien["credits_restants"] == credits_du_plan("essentiel")


# ---------------------------------------------------------------------
# Une transaction n'ouvre qu'un abonnement
# ---------------------------------------------------------------------


def test_deux_rappels_identiques_n_ouvrent_qu_un_mois(client, abonne, collecte_simulee):
    """LE TROISIEME TEST CENTRAL.

    Le rappel signe et la verification du navigateur peuvent arriver
    ensemble, et CamPay reessaie ses rappels. Sans idempotence, un seul
    paiement ouvrirait deux mois.
    """
    identifiant, entete = abonne
    client.post(
        "/moi/abonnement/payer",
        json={"forfait": "cabinet", "telephone": "699000000"},
        headers=entete,
    )
    rappel = {
        "status": campay.REUSSI,
        "reference": _reference(identifiant),
        "signature": _signature(),
    }

    client.post("/paiements/campay", json=rappel)
    premiere = client.get("/moi/abonnement", headers=entete).json()["echeance"]
    client.post("/paiements/campay", json=rappel)
    seconde = client.get("/moi/abonnement", headers=entete).json()

    assert seconde["echeance"] == premiere
    assert seconde["credits_restants"] == credits_du_plan("cabinet")


def test_un_paiement_en_cours_empeche_d_en_lancer_un_second(
    client, abonne, collecte_simulee
):
    _, entete = abonne
    client.post(
        "/moi/abonnement/payer",
        json={"forfait": "essentiel", "telephone": "699000000"},
        headers=entete,
    )

    seconde = client.post(
        "/moi/abonnement/payer",
        json={"forfait": "cabinet", "telephone": "699000000"},
        headers=entete,
    )

    assert seconde.status_code == 409


# ---------------------------------------------------------------------
# Suivi du paiement
# ---------------------------------------------------------------------


def test_le_serveur_lit_l_etat_chez_campay_et_ouvre_l_abonnement(
    client, abonne, collecte_simulee, monkeypatch
):
    """C'est la lecture SERVEUR qui fait foi, pas ce que dit le navigateur."""
    identifiant, entete = abonne
    client.post(
        "/moi/abonnement/payer",
        json={"forfait": "essentiel", "telephone": "699000000"},
        headers=entete,
    )
    monkeypatch.setattr(
        campay,
        "etat",
        lambda ref: {
            "reference": ref,
            "statut": campay.REUSSI,
            "operateur": "MTN",
            "reference_operateur": "MTN-9",
        },
    )

    suivi = client.get("/moi/abonnement/paiement", headers=entete).json()

    assert suivi["statut"] == campay.REUSSI
    assert suivi["abonnement"]["forfait"]["code"] == "essentiel"


def test_un_paiement_echoue_libere_la_demande(
    client, abonne, collecte_simulee, monkeypatch
):
    """Sinon une demande morte bloquerait toute nouvelle tentative."""
    _, entete = abonne
    client.post(
        "/moi/abonnement/payer",
        json={"forfait": "essentiel", "telephone": "699000000"},
        headers=entete,
    )
    monkeypatch.setattr(
        campay,
        "etat",
        lambda ref: {"reference": ref, "statut": campay.ECHOUE, "operateur": "MTN",
                     "reference_operateur": None},
    )

    suivi = client.get("/moi/abonnement/paiement", headers=entete).json()

    assert suivi["statut"] == campay.ECHOUE
    assert client.get("/moi/abonnement", headers=entete).json()["demande_en_attente"] is None


def test_un_numero_refuse_ne_laisse_pas_de_demande_fantome(client, abonne, monkeypatch):
    """Une demande restee en attente sur un paiement jamais parti
    bloquerait toute nouvelle tentative."""
    _, entete = abonne

    def refuser(**_):
        raise campay.PaiementRefuse("Numero invalide.")

    monkeypatch.setattr(campay, "collecter", refuser)

    reponse = client.post(
        "/moi/abonnement/payer",
        json={"forfait": "essentiel", "telephone": "000"},
        headers=entete,
    )

    assert reponse.status_code == 422
    assert client.get("/moi/abonnement", headers=entete).json()["demande_en_attente"] is None


# ---------------------------------------------------------------------
# Numero de telephone
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "saisi",
    ["699000000", "+237699000000", "237699000000", "00237699000000", "6 99 00 00 00"],
)
def test_les_formes_usuelles_d_un_numero_sont_acceptees(saisi):
    """Les gens ecrivent leur numero comme ils le disent.

    Refuser ces formes ferait echouer des paiements pour une question
    de mise en page.
    """
    assert campay.normaliser_numero(saisi) == "237699000000"


@pytest.mark.parametrize("saisi", ["", "12345", "23769900000012345", "abcdefghi"])
def test_un_numero_invalide_est_refuse_avant_tout_appel(saisi):
    with pytest.raises(campay.PaiementRefuse):
        campay.normaliser_numero(saisi)
