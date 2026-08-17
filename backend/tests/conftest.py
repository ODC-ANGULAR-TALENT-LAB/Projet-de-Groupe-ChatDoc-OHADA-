"""Outillage commun aux tests.

Les scripts d'ingestion portent des noms numerotes (1_extraire.py,
2_decouper.py) imposes par le guide de realisation. Un nom qui commence
par un chiffre n'est pas un identifiant Python valide : on ne peut pas
les importer normalement, il faut les charger a la main.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

BACKEND = Path(__file__).resolve().parents[1]
INGESTION = BACKEND / "ingestion"

# chemins.py est importe par les scripts d'ingestion ; backend/ permet
# d'importer app.services directement dans les tests.
sys.path.insert(0, str(INGESTION))
sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402


def charger_module(nom: str, fichier: str) -> ModuleType:
    """Charge un script d'ingestion sous un nom utilisable."""
    specification = importlib.util.spec_from_file_location(
        nom, INGESTION / fichier
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def decoupeur() -> ModuleType:
    return charger_module("decoupeur", "2_decouper.py")


@pytest.fixture(scope="session")
def controleur() -> ModuleType:
    return charger_module("controleur", "controler.py")


@pytest.fixture(scope="session")
def extracteur() -> ModuleType:
    """1_extraire.py. Construire le module n'appelle ni Tesseract ni le
    reseau : ces tests tournent sans OCR installe."""
    return charger_module("extracteur", "1_extraire.py")


@pytest.fixture(scope="session")
def provenancier() -> ModuleType:
    """0_provenance.py. Ne fait que lire des fichiers et calculer un
    condensat : aucun reseau, aucune base."""
    return charger_module("provenancier", "0_provenance.py")


@pytest.fixture(scope="session")
def vectoriseur() -> ModuleType:
    """4_vectoriser.py. Construire le moteur SQLAlchemy n'ouvre aucune
    connexion : ces tests tournent sans base."""
    return charger_module("vectoriseur", "4_vectoriser.py")


def article(identifiant: int, numero: str, **scores) -> dict:
    """Article minimal pour les tests de fusion."""
    return {
        "id": identifiant,
        "numero": numero,
        "chemin": "Livre I > Titre II",
        "contenu": "Contenu de l'article.",
        "sigle": "AUSCGIE",
        **scores,
    }
