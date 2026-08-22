"""Point d'entree de l'API ChatDocs OHADA.

Lancement, depuis le dossier backend/ :
    uvicorn app.main:app --reload
"""

import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import parametres
from app.db import moteur
from app.routers import (
    admin,
    auth,
    avis,
    calculateurs,
    chat,
    conformite,
    corpus,
    favoris,
    forfaits,
    generateur,
    profil,
)

app = FastAPI(
    title="ChatDocs OHADA",
    description=(
        "Assistant de recherche juridique et fiscale pour l'espace OHADA "
        "et le Cameroun. Chaque reponse cite son article.\n\n"
        "Aide a la recherche documentaire : ne constitue ni une "
        "consultation juridique, ni un conseil fiscal."
    ),
    version="0.2.0",
)

journal = logging.getLogger(__name__)


def _alerter_origines_injoignables() -> None:
    """Crie si une origine autorisee ne peut venir d'aucun navigateur.

    POURQUOI CE GARDE-FOU EXISTE. `ORIGINES_AUTORISEES` a ete alimente
    par `fromService: { property: host }` sur Render, qui renvoie l'hote
    du RESEAU PRIVE : « chatdocs-web », sans domaine. L'API a donc
    autorise une origine qu'aucun navigateur n'envoie, et le site en
    ligne ne fonctionnait pas.

    Rien ne le signalait. Le deploiement etait vert, /sante repondait,
    les journaux etaient vides — puisqu'une requete bloquee par CORS
    n'atteint jamais l'API. Le seul symptome visible etait une
    application qui ne repond a rien.

    Un nom d'hote public porte toujours un point. Un hote de reseau
    prive, jamais. Le critere est grossier, mais il attrape exactement
    la faute commise.

    LE CONTROLE NE S'APPLIQUE QU'EN PRODUCTION. En developpement,
    `localhost` ne porte pas de point non plus : sans cette garde, tout
    le monde verrait l'alerte a chaque demarrage local, et une alerte
    permanente cesse d'etre lue — ce qui la rendrait inutile le jour ou
    elle compte.
    """
    if not parametres.production:
        return

    suspectes = [
        origine
        for origine in parametres.liste_origines
        if "." not in (urlparse(origine).hostname or "")
    ]
    if suspectes:
        journal.error(
            "ORIGINES_AUTORISEES contient %s : un hote sans point est un "
            "hote de reseau prive, qu'aucun navigateur n'enverra comme "
            "Origin. Le site sera en ligne et ne fonctionnera pas. "
            "Attendu : le domaine public complet, par exemple "
            "https://chatdocs-web.onrender.com",
            ", ".join(suspectes),
        )


_alerter_origines_injoignables()

# CORS restreint aux origines declarees. En production, une seule :
# le domaine du frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=parametres.liste_origines,
    allow_credentials=True,
    # PUT (profil, photo, favoris) et PATCH (changement de role) etaient
    # absents de cette liste.
    #
    # UNE METHODE MANQUANTE NE SE VOIT PAS COTE SERVEUR : la route
    # repond parfaitement a curl. C'est le NAVIGATEUR qui refuse
    # d'envoyer la requete apres la reponse preliminaire, et l'appel
    # echoue sans jamais atteindre l'API — donc sans laisser la moindre
    # trace dans les journaux.
    #
    # On enumere plutot que d'ouvrir a "*" : la liste dit ce que l'API
    # accepte reellement. Un test verifie qu'aucune methode exposee n'en
    # est absente (tests/test_routes.py).
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def entetes_securite(requete: Request, appeler_suivant):
    """En-tetes de securite sur chaque reponse.

    HSTS n'est pose qu'en production : en developpement, il forcerait le
    navigateur a passer localhost en HTTPS et rendrait l'API
    injoignable, avec un cache difficile a purger.
    """
    reponse = await appeler_suivant(requete)
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["X-Frame-Options"] = "DENY"
    reponse.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if parametres.production:
        reponse.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return reponse


app.include_router(auth.routeur)
app.include_router(chat.routeur)
app.include_router(corpus.routeur)
app.include_router(conformite.routeur)
app.include_router(calculateurs.routeur)
app.include_router(favoris.routeur)
app.include_router(generateur.routeur)
app.include_router(profil.routeur)
app.include_router(avis.routeur)
app.include_router(forfaits.routeur)
app.include_router(admin.routeur)


@app.get("/", tags=["technique"])
def racine() -> dict:
    """Verifie simplement que l'API repond."""
    return {"service": "ChatDocs OHADA", "version": app.version}


@app.get("/sante", tags=["technique"])
def sante() -> dict:
    """Etat de l'API, de sa base et de son corpus.

    Le compte d'articles vectorises n'est pas decoratif : sans
    embeddings, la moitie vectorielle de la recherche ne remonte rien et
    le systeme se degrade silencieusement en recherche plein texte.
    """
    etat: dict = {"api": "ok"}

    # L'ETAT DES FOURNISSEURS EST LA PREMIERE CHOSE A REGARDER.
    #
    # Sans cle de redaction, le produit ne tombe pas : il rend les
    # articles bruts, avec un message expliquant que la synthese est
    # indisponible. C'est le bon comportement — mais il est INDISCERNABLE
    # d'un modele qui repondrait mal, et la panne se decouvre alors par
    # une mauvaise reponse plutot que par un indicateur.
    #
    # Ces deux lignes disent en une requete ce qu'il fallait auparavant
    # deduire du contenu d'une reponse.
    etat["redaction"] = "ok" if parametres.llm_configure else "non configuree"
    etat["embeddings"] = (
        "ok" if parametres.embeddings_configures else "non configures"
    )

    try:
        with moteur.connect() as cx:
            extensions = (
                cx.execute(
                    text(
                        "SELECT extname FROM pg_extension "
                        "WHERE extname IN ('vector', 'citext')"
                    )
                )
                .scalars()
                .all()
            )
            etat["base"] = "ok"
            etat["extensions"] = sorted(extensions)
            etat["textes"] = cx.execute(text("SELECT count(*) FROM texte")).scalar()
            etat["articles"] = cx.execute(text("SELECT count(*) FROM article")).scalar()
            etat["articles_vectorises"] = cx.execute(
                text("SELECT count(embedding) FROM article")
            ).scalar()
    except Exception as erreur:  # noqa: BLE001 - on veut le diagnostic brut
        etat["base"] = "indisponible"
        # Le detail expose la chaine de connexion et la topologie interne :
        # utile en developpement, a ne pas publier.
        if not parametres.production:
            etat["detail"] = str(erreur)
    return etat
