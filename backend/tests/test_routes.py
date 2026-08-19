"""Test de fumee : chaque route repond-elle, et est-elle bien protegee ?

CE QUE CE FICHIER ATTRAPE. Une route ajoutee sans dependance
d'authentification, un schema de sortie qui ne correspond plus au
modele, un routeur oublie dans main.py. Rien de tout cela ne se voit en
lisant le code, et tout se decouvre au pire moment.

Ces tests ne touchent pas la base : ils verifient le contrat HTTP, pas
les donnees.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# Routes qui doivent etre accessibles SANS compte. La bibliotheque et la
# transparence en font partie : une transparence qu'il faudrait un
# compte pour consulter n'en serait pas une.
ROUTES_PUBLIQUES = [
    "/",
    "/sante",
    "/textes",
    "/provenance",
    "/journal",
    "/conformite/modeles",
    "/documents/modeles",
    "/moi/preferences/catalogue",
    # Le catalogue des calculateurs est public : il ne calcule rien et
    # dit surtout lesquels ont, ou n'ont pas, de base legale en corpus.
    "/calculateurs",
]

# Routes qui doivent exiger un jeton. Une seule oubliee, et des donnees
# ou un cout d'appel partent sans controle.
ROUTES_PROTEGEES = [
    ("GET", "/moi/quota"),
    ("GET", "/moi/profil"),
    ("PUT", "/moi/profil"),
    ("PUT", "/moi/photo"),
    ("DELETE", "/moi/photo"),
    ("GET", "/conversations"),
    ("POST", "/chat/question"),
    ("POST", "/chat/question/flux"),
    ("POST", "/signalements"),
    ("GET", "/messages/1/export"),
    ("POST", "/conformite/analyser"),
    ("POST", "/documents/statuts_sarl"),
    ("GET", "/favoris"),
    ("PUT", "/favoris/1"),
    ("DELETE", "/favoris/1"),
    ("GET", "/veille"),
    ("POST", "/calculateurs/tva"),
    ("POST", "/calculateurs/is"),
    ("POST", "/calculateurs/irpp"),
    ("POST", "/calculateurs/patente"),
    ("GET", "/admin/depots"),
    ("GET", "/admin/corpus/etat"),
    ("GET", "/admin/utilisateurs"),
]


@pytest.mark.parametrize("chemin", ROUTES_PUBLIQUES)
def test_une_route_publique_ne_demande_pas_de_jeton(client, chemin):
    reponse = client.get(chemin)

    # 200 ou 503 (base indisponible) : ce qui compte est qu'on ne se
    # heurte pas a un 401, et que la route existe.
    assert reponse.status_code != 401, chemin
    assert reponse.status_code != 404, chemin


@pytest.mark.parametrize("methode,chemin", ROUTES_PROTEGEES)
def test_une_route_protegee_refuse_sans_jeton(client, methode, chemin):
    reponse = client.request(methode, chemin, json={})

    assert reponse.status_code == 401, f"{methode} {chemin} n'exige pas de jeton"


def test_toutes_les_routes_declarees_sont_montees(client):
    """Un routeur oublie dans main.py ne se voit pas autrement.

    On lit le schema OpenAPI plutot que `app.routes` : celui-ci melange
    des routes et des routeurs inclus, qui n'ont pas de chemin propre.
    Le schema, lui, est ce que le serveur expose reellement.
    """
    chemins = set(app.openapi()["paths"])

    for attendu in [
        "/chat/question",
        "/chat/question/flux",
        "/signalements",
        "/provenance",
        "/journal",
        "/conformite/modeles",
        "/conformite/analyser",
        "/documents/modeles",
        "/documents/modeles/{cle}/questionnaire",
        "/moi/profil",
        "/moi/preferences/catalogue",
        "/moi/photo",
        "/utilisateurs/{utilisateur_id}/photo",
        "/documents/{cle}",
        "/favoris",
        "/favoris/{article_id}",
        "/veille",
        "/calculateurs",
        "/calculateurs/tva",
        "/calculateurs/is",
        "/calculateurs/irpp",
        "/calculateurs/patente",
        "/admin/depots",
        "/admin/depots/{depot_id}/analyser",
        "/admin/depots/{depot_id}/relu",
        "/admin/textes/{texte_id}/vectoriser",
        "/admin/utilisateurs/{utilisateur_id}/role",
    ]:
        assert attendu in chemins, f"route absente : {attendu}"


def test_toutes_les_methodes_utilisees_sont_autorisees_par_le_cors(client):
    """LE DÉFAUT QUE CE TEST EMPÊCHE DE REVENIR.

    `allow_methods` listait GET, POST et DELETE. Les routes en PUT —
    profil, photo, favoris — répondaient parfaitement à curl, mais le
    NAVIGATEUR refusait d'envoyer la requête après la réponse
    préliminaire : l'appel échouait sans jamais atteindre l'API.

    Une panne côté serveur se voit dans les journaux ; celle-ci ne se
    voit que dans la console du navigateur. D'où ce test.
    """
    autorisees = set()
    for couche in app.user_middleware:
        options = getattr(couche, "kwargs", {}) or {}
        if "allow_methods" in options:
            autorisees = {m.upper() for m in options["allow_methods"]}

    assert autorisees, "aucun middleware CORS déclarant allow_methods"

    utilisees = set()
    for chemin, operations in app.openapi()["paths"].items():
        for methode in operations:
            if methode.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                utilisees.add(methode.upper())

    manquantes = utilisees - autorisees
    assert not manquantes, (
        f"méthode(s) exposée(s) mais bloquée(s) par le CORS : "
        f"{sorted(manquantes)}"
    )
