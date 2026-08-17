"""Emplacements de travail du pipeline d'ingestion.

Les scripts d'ingestion se lancent depuis le dossier backend/, mais le
corpus n'appartient pas au code de l'API : il vit a la racine du depot.
Un seul endroit resout ces chemins.
"""

import sys
from pathlib import Path

# ingestion/ -> backend/ -> racine du monorepo
BACKEND = Path(__file__).resolve().parents[1]
RACINE = Path(__file__).resolve().parents[2]

# Les scripts d'ingestion se lancent par leur chemin (python
# ingestion/3_charger.py) : seul ingestion/ se retrouve dans sys.path.
# On y ajoute backend/ pour que "from app.config import parametres"
# fonctionne, plutot que de dupliquer la lecture du .env.
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# PDF officiels et leurs fiches de provenance.
# Ignore par Git (sauf les *.provenance.json) : les PDF sont volumineux
# et se retelechargent depuis leur source officielle.
DOSSIER_SOURCES = RACINE / "sources"

# Fichiers intermediaires du pipeline : texte brut, articles decoupes.
# Entierement ignore par Git : tout se regenere a partir du PDF.
DOSSIER_SORTIE = Path(__file__).resolve().parent / "sortie"


def preparer_dossiers() -> None:
    """Cree les dossiers de travail s'ils n'existent pas encore."""
    DOSSIER_SOURCES.mkdir(exist_ok=True)
    DOSSIER_SORTIE.mkdir(exist_ok=True)
