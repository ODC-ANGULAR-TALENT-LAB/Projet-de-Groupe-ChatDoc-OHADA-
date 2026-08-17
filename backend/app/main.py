"""Point d'entree de l'API ChatDocs OHADA.

Lancement, depuis le dossier backend/ :
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import parametres
from app.db import moteur
from app.routers import (
    admin,
    auth,
    calculateurs,
    chat,
    conformite,
    corpus,
    favoris,
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

# CORS restreint aux origines declarees. En production, une seule :
# le domaine du frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=parametres.liste_origines,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
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
