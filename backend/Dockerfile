# API ChatDocs OHADA — image de production.
#
# Utilisable telle quelle sur Railway ou Render. Les scripts
# d'ingestion ne sont PAS lances ici : l'ingestion du corpus est un
# processus hors ligne, declenche manuellement, jamais pendant qu'un
# utilisateur attend une reponse.
#
# -----------------------------------------------------------------
# LE CONTEXTE DE BUILD EST LA RACINE DU DEPOT, PAS backend/
# -----------------------------------------------------------------
# C'est pourquoi chaque COPY est prefixe par `backend/`. La raison est
# `db/` : les migrations vivent a la racine, hors de backend/, et
# doivent entrer dans l'image pour etre jouees au demarrage. Un
# contexte limite a backend/ ne peut pas les atteindre — Docker refuse
# tout COPY qui remonte au-dessus du contexte.
#
# render.yaml declare donc `dockerContext: .`. En local :
#
#   docker build -f backend/Dockerfile -t chatdocs-api .
#
# L'ARBORESCENCE DU DEPOT EST REPRODUITE dans l'image (/app/backend et
# /app/db) et non aplatie. `config.py` et `appliquer_migrations.py`
# localisent la racine par `parents[2]` a partir de leur propre
# fichier : aplatir les dossiers ferait pointer cette racine sur `/`,
# et le script chercherait les migrations dans /db.

FROM python:3.12-slim

# Ne pas ecrire de .pyc, ne pas tamponner la sortie : les journaux
# doivent arriver en temps reel dans la console de l'hebergeur.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Tolerance reseau : un delai passager vers PyPI ne doit pas faire
    # echouer un deploiement.
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

WORKDIR /app

# Les dependances d'abord : cette couche ne se reconstruit que si
# requirements.txt change.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app ./backend/app
COPY backend/scripts ./backend/scripts
COPY db ./db

# Un utilisateur non privilegie : le conteneur n'a aucune raison de
# tourner en root.
RUN useradd --create-home --uid 10001 chatdocs
USER chatdocs

EXPOSE 8000

# Invoque par `sh` plutot qu'en executable direct : le bit +x d'un
# fichier ne survit pas toujours a un depot clone depuis Windows, et
# l'echec serait un « permission denied » au demarrage, sans rapport
# apparent avec le systeme de fichiers.
CMD ["sh", "/app/backend/scripts/demarrer_conteneur.sh"]
