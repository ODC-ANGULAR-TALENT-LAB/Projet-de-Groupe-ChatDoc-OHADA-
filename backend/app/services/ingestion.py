"""Ingestion d'un PDF televerse par un administrateur.

Extraction -> decoupage -> controles. Rien de plus : cette fonction ne
touche JAMAIS au corpus interrogeable. Elle produit un depot en attente,
que seule une validation humaine explicite fait entrer en base.

C'est la traduction technique d'un interdit du cahier des charges :
ingerer un PDF sans verification d'origine ni de date est precisement
le probleme que ce produit pretend resoudre.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from app.services.controles import AVERTISSEMENT, controler
from app.services.decoupage import decouper_texte
from app.services.extraction import extraire

journal = logging.getLogger(__name__)

# En dessous de cette moyenne de caracteres par page, le PDF est
# considere comme scanne : il n'y a pas de couche de texte a extraire.
SEUIL_PAGE_SCANNEE = 100

# Garde-fou memoire : un acte uniforme depasse rarement quelques Mo.
TAILLE_MAXIMALE = 60 * 1024 * 1024


class DepotRefuse(Exception):
    """Le fichier ne peut pas etre traite."""


@dataclass
class ResultatIngestion:
    sha256: str
    nb_pages: int
    extrait_par_ocr: bool
    articles: list[dict] = field(default_factory=list)
    problemes: list[dict] = field(default_factory=list)


def extraire_pages(contenu: bytes) -> tuple[list[tuple[int, str]], bool, dict]:
    """Extrait le texte page par page. Signale un PDF scanne.

    L'extraction respecte les mises en page sur deux colonnes et retire
    les en-tetes repetes : voir app/services/extraction.py.
    """
    try:
        pages, diagnostic = extraire(contenu)
    except Exception as erreur:  # noqa: BLE001 - diagnostic utile a l'admin
        raise DepotRefuse(
            "Ce fichier n'a pas pu etre lu comme un PDF. Verifie qu'il "
            "n'est pas protege par mot de passe ni endommage."
        ) from erreur

    if not pages:
        raise DepotRefuse("Ce PDF ne contient aucune page.")

    return pages, diagnostic["caracteres_par_page"] < SEUIL_PAGE_SCANNEE, diagnostic


def assembler_texte(pages: list[tuple[int, str]]) -> str:
    """Reconstitue le texte pagine attendu par le decoupage."""
    return "".join(f"\n===PAGE {numero}===\n{texte}" for numero, texte in pages)


def ingerer(
    contenu: bytes,
    page_debut: int = 1,
    page_fin: int | None = None,
) -> ResultatIngestion:
    """Prepare un depot a partir du contenu d'un PDF.

    `page_debut` sert a ecarter le sommaire, qui produirait sinon autant
    de faux articles que d'entrees.
    """
    if not contenu:
        raise DepotRefuse("Fichier vide.")
    if len(contenu) > TAILLE_MAXIMALE:
        raise DepotRefuse(
            f"Fichier trop volumineux ({len(contenu) // 1024 // 1024} Mo). "
            f"Limite : {TAILLE_MAXIMALE // 1024 // 1024} Mo."
        )
    if not contenu.startswith(b"%PDF"):
        raise DepotRefuse("Ce fichier n'est pas un PDF.")

    pages, scanne, diagnostic = extraire_pages(contenu)

    if scanne:
        # L'OCR exige Tesseract et son pack francais, absents du
        # conteneur de production. Refuser explicitement vaut mieux que
        # de charger un texte vide : un corpus qui a l'air rempli mais
        # ne contient rien est pire qu'un refus.
        raise DepotRefuse(
            "Ce PDF semble etre un scan : aucune couche de texte exploitable. "
            "Il faut passer par l'OCR en ligne de commande "
            "(ingestion/1_extraire.py), puis relire un echantillon a l'oeil "
            "avant de deposer. L'OCR confond 0/O et 1/l — dans un texte "
            "juridique, un numero d'article errone est pire qu'une absence."
        )

    articles = decouper_texte(assembler_texte(pages), page_debut, page_fin)
    if not articles:
        raise DepotRefuse(
            "Aucun article reconnu dans ce document. Les en-tetes ne "
            "ressemblent probablement pas a « Article N ». Verifie aussi la "
            "page de depart si le document commence par un sommaire."
        )

    problemes = [
        {"niveau": niveau, "message": message}
        for niveau, message in controler(articles)
    ]

    # Ce que la mise en page a impose : l'administrateur doit le savoir
    # avant de relire. Un document sur deux colonnes se relit autrement
    # qu'un document lineaire.
    if diagnostic["pages_deux_colonnes"]:
        problemes.insert(
            0,
            {
                "niveau": AVERTISSEMENT,
                "message": (
                    f"Mise en page sur deux colonnes detectee sur "
                    f"{diagnostic['pages_deux_colonnes']} page(s) sur "
                    f"{diagnostic['pages']}. Les colonnes ont ete lues "
                    "separement, mais relis particulierement les articles "
                    "a cheval sur une coupure de colonne."
                ),
            },
        )
    if diagnostic["lignes_repetees_retirees"]:
        apercu = " | ".join(diagnostic["lignes_repetees_retirees"][:3])
        problemes.insert(
            0,
            {
                "niveau": AVERTISSEMENT,
                "message": (
                    f"{len(diagnostic['lignes_repetees_retirees'])} en-tete(s) "
                    f"ou pied(s) de page retire(s) : {apercu[:150]}"
                ),
            },
        )

    return ResultatIngestion(
        sha256=hashlib.sha256(contenu).hexdigest(),
        nb_pages=len(pages),
        extrait_par_ocr=False,
        articles=articles,
        problemes=problemes,
    )
