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
