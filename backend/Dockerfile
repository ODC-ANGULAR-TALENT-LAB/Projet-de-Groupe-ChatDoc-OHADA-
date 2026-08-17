# API ChatDocs OHADA — image de production.
#
# Utilisable telle quelle sur Railway ou Render. Les scripts
# d'ingestion ne sont PAS lances ici : l'ingestion du corpus est un
# processus hors ligne, declenche manuellement, jamais pendant qu'un
# utilisateur attend une reponse.

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
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Un utilisateur non privilegie : le conteneur n'a aucune raison de
# tourner en root.
RUN useradd --create-home --uid 10001 chatdocs
USER chatdocs

EXPOSE 8000

# $PORT est impose par Railway et Render ; 8000 sert de repli en local.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
