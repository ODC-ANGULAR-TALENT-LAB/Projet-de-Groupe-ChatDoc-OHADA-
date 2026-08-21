"""Ce dont depend le deploiement sur Render.

Ces cas ne testent pas une fonctionnalite du produit mais un CABLAGE :
les adresses de l'API et du site ne sont ecrites nulle part, elles sont
injectees par Render sous forme de noms d'hotes nus. Si la
normalisation casse, l'application se deploie sans erreur et echoue
uniquement dans le navigateur, sur un blocage CORS — le pire des
symptomes a diagnostiquer.
"""

from app.config import Parametres


def _origines(valeur: str) -> list[str]:
    return Parametres(origines_autorisees=valeur).liste_origines


def test_hote_nu_recoit_https():
    """Ce que livre `fromService: { property: host }` sur Render."""
    assert _origines("chatdocs-web.onrender.com") == [
        "https://chatdocs-web.onrender.com"
    ]


def test_url_complete_est_laissee_intacte():
    assert _origines("https://chatdocs.cm") == ["https://chatdocs.cm"]


def test_localhost_en_clair_reste_en_clair():
    """Le developpement local ne doit pas basculer en HTTPS."""
    assert _origines("http://localhost:4200") == ["http://localhost:4200"]


def test_barre_finale_retiree():
    """CORS compare des chaines : la barre finale ne correspondrait pas."""
    assert _origines("https://chatdocs.cm/") == ["https://chatdocs.cm"]


def test_liste_mixte_et_entrees_vides():
    """Une virgule en trop ne doit pas produire une origine vide.

    Une chaine vide dans la liste serait comparee a l'en-tete `Origin`
    et n'y correspondrait jamais : sans filtrage, elle passe inapercue.
    """
    assert _origines("http://localhost:4200, chatdocs-web.onrender.com, ") == [
        "http://localhost:4200",
        "https://chatdocs-web.onrender.com",
    ]
