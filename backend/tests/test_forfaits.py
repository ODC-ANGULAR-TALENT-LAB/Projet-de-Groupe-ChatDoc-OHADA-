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
    FORFAITS_PAR_DEFAUT,
    oublier_le_cache,
    par_code,
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


@pytest.mark.parametrize(
    "f",
    [f for f in FORFAITS_PAR_DEFAUT if f.prix_fcfa > 0 and not f.essai],
    ids=lambda f: f.code,
)
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
    for f in FORFAITS_PAR_DEFAUT:
        # Le forfait d'essai est un montant symbolique : l'y soumettre
        # obligerait a truquer le cout pour faire passer le test.
        if f.prix_fcfa == 0 or f.essai:
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

    payants = [f for f in FORFAITS_PAR_DEFAUT if f.prix_fcfa > 0 and not f.essai]
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
    # Le forfait d'essai s'intercale hors production.
    assert "gratuit" in codes and "essentiel" in codes and "cabinet" in codes


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


# ---------------------------------------------------------------------
# Un compte de personnel n'est pas un client
# ---------------------------------------------------------------------


@pytest.fixture
def juriste():
    email = "essai-forfait-juriste@chatdocs-ohada.cm"
    identifiant = _compte(email, role="juriste")
    yield identifiant, {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    _effacer(email)


@pytest.mark.parametrize("role", ["juriste", "admin"])
def test_le_personnel_ne_souscrit_pas_de_forfait(client, role):
    """LE TEST QUI PORTE LA REGLE.

    Un juriste depose et valide des textes ; un administrateur tient le
    service. Ni l'un ni l'autre n'achete un forfait. Leur en vendre un
    gonflerait le chiffre d'affaires d'une vente interne, et n'aurait
    aucun effet utile puisqu'ils sont deja exemptes du quota.
    """
    email = f"essai-personnel-{role}@chatdocs-ohada.cm"
    identifiant = _compte(email, role=role)
    entete = {"Authorization": f"Bearer {creer_jeton(identifiant)}"}
    try:
        reponse = client.post(
            "/moi/abonnement", json={"forfait": "essentiel"}, headers=entete
        )
        assert reponse.status_code == 409

        paiement = client.post(
            "/moi/abonnement/payer",
            json={"forfait": "essentiel", "telephone": "699000000"},
            headers=entete,
        )
        assert paiement.status_code == 409
    finally:
        _effacer(email)


def test_l_abonnement_du_personnel_se_declare_comme_tel(client, juriste):
    """L'interface doit pouvoir le dire plutot que d'afficher des
    boutons qui repondront 409."""
    _, entete = juriste

    mien = client.get("/moi/abonnement", headers=entete).json()

    assert mien["personnel"] is True


def test_un_client_ordinaire_n_est_pas_marque_personnel(client, abonne):
    _, entete = abonne

    assert client.get("/moi/abonnement", headers=entete).json()["personnel"] is False


def test_le_personnel_est_exempte_du_quota():
    """Un juriste doit pouvoir interroger l'assistant autant qu'il le
    faut pour verifier les citations d'un texte qu'il vient d'ingerer.

    On verifie la PROPRIETE du modele : la garde des routes de chat s'y
    adosse, et c'est elle qui doit rester vraie.
    """
    from app.models import Utilisateur

    for role, attendu in (
        ("utilisateur", False),
        ("juriste", True),
        ("admin", True),
    ):
        compte = Utilisateur(email=f"x-{role}@essai.cm", role=role)
        assert compte.est_personnel is attendu


def test_le_personnel_ne_compte_pas_dans_les_abonnes(client, patron):
    """Sinon le chiffre d'affaires afficherait des ventes internes."""
    email = "essai-personnel-compte@chatdocs-ohada.cm"
    identifiant = _compte(email, role="juriste")
    with FabriqueSession() as session:
        session.execute(
            text(
                "UPDATE utilisateur SET plan = 'cabinet', "
                "plan_echeance = CURRENT_DATE + 30 WHERE id = :id"
            ),
            {"id": identifiant},
        )
        session.commit()
    try:
        bord = client.get("/admin/tableau-de-bord", headers=patron).json()
        assert bord["abonnes_par_forfait"].get("cabinet", 0) == 0
    finally:
        _effacer(email)


# ---------------------------------------------------------------------
# Le catalogue est modifiable, et la marge le protege toujours
#
# LE CATALOGUE A QUITTE LE CODE POUR LA BASE. Tant qu'il y vivait, un
# test refusait toute grille sous le plancher. Une table modifiable
# depuis une console ne passe par AUCUN test : la verification a du
# migrer vers l'ecriture. Ces tests verifient qu'elle y est bien, et
# qu'elle mord.
# ---------------------------------------------------------------------


def test_creer_un_forfait_a_perte_est_refuse(client, patron):
    """LE TEST QUI REMPLACE L'ANCIEN GARDE-FOU.

    Sans lui, sortir le catalogue du code aurait echange une garantie
    mecanique contre une bonne intention : rien n'empecherait plus
    d'ouvrir 100 credits a 200 F depuis l'interface.
    """
    reponse = client.post(
        "/admin/forfaits",
        json={
            "code": "essai-perdant",
            "libelle": "Perdant",
            "prix_fcfa": 200,
            "credits": 100,
        },
        headers=patron,
    )

    assert reponse.status_code == 422
    # Le message doit dire COMBIEN serait tenable : sans ce chiffre,
    # l'administrateur essaie des valeurs au hasard.
    assert "crédits" in reponse.json()["detail"]


def test_creer_un_forfait_soutenable_est_accepte(client, patron):
    try:
        reponse = client.post(
            "/admin/forfaits",
            json={
                "code": "essai-tenable",
                "libelle": "Tenable",
                "prix_fcfa": 3000,
                "credits": 50,
                "argumentaire": "Créé par un test.",
                "atouts": ["50 questions"],
            },
            headers=patron,
        )
        assert reponse.status_code == 201
        assert reponse.json()["marge"] >= 0.5
    finally:
        with FabriqueSession() as session:
            session.execute(
                text("DELETE FROM forfait WHERE code = 'essai-tenable'")
            )
            session.commit()
        oublier_le_cache()


def test_modifier_un_forfait_repasse_par_la_verification(client, patron):
    """Modifier est aussi dangereux que creer : gonfler les credits d'un
    forfait existant le rendrait perdant sans qu'aucune creation n'ait
    eu lieu."""
    reponse = client.put(
        "/admin/forfaits/essentiel",
        json={
            "libelle": "Essentiel",
            "prix_fcfa": 5000,
            "credits": 500,
            "atouts": [],
        },
        headers=patron,
    )

    assert reponse.status_code == 422


def test_le_forfait_gratuit_ne_se_desactive_pas(client, patron):
    """C'est celui sur lequel tout compte retombe, a l'inscription comme
    a l'echeance d'un abonnement. Sans lui, une inscription n'aurait
    plus de plan."""
    reponse = client.put(
        "/admin/forfaits/gratuit",
        json={
            "libelle": "Découverte",
            "prix_fcfa": 0,
            "credits": 10,
            "atouts": [],
            "actif": False,
        },
        headers=patron,
    )

    assert reponse.status_code == 409


def test_un_utilisateur_ordinaire_ne_touche_pas_au_catalogue(client, abonne):
    _, entete = abonne

    assert client.get("/admin/forfaits", headers=entete).status_code == 403
    assert (
        client.post(
            "/admin/forfaits",
            json={"code": "pirate", "libelle": "Pirate", "prix_fcfa": 1, "credits": 999},
            headers=entete,
        ).status_code
        == 403
    )


# ---------------------------------------------------------------------
# Les comptes sans souscription sont des abonnes Decouverte
# ---------------------------------------------------------------------


def test_les_comptes_sans_souscription_comptent_comme_decouverte(client, abonne, patron):
    """QUELQU'UN QUI N'A RIEN SOUSCRIT EST ABONNE A DECOUVERTE, ce n'est
    pas une absence d'abonnement.

    La repartition les excluait : elle laissait une colonne vide la ou
    se trouve le gros des comptes, et devenait illisible.
    """
    bord = client.get("/admin/tableau-de-bord", headers=patron).json()

    assert bord["abonnes_par_forfait"].get("gratuit", 0) >= 1
    # Le revenu, lui, ne compte que le payant.
    assert bord["revenu_mensuel_fcfa"] == sum(
        par_code()[code].prix_fcfa * n
        for code, n in bord["abonnes_par_forfait"].items()
        if code in par_code() and par_code()[code].prix_fcfa > 0
    )


def test_les_abonnes_payants_excluent_le_gratuit(client, patron):
    """« Abonnes payants » garde son sens strict : ceux qui paient."""
    bord = client.get("/admin/tableau-de-bord", headers=patron).json()

    assert bord["abonnes_payants"] <= sum(bord["abonnes_par_forfait"].values())
    assert bord["abonnes_payants"] == sum(
        n
        for code, n in bord["abonnes_par_forfait"].items()
        if code in par_code() and par_code()[code].prix_fcfa > 0
    )
