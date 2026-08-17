"""Analyse de conformite d'un document depose par l'utilisateur.

LE FICHIER N'EST JAMAIS ECRIT SUR LE DISQUE. Il arrive en memoire, il
est lu, il est oublie a la fin de la requete. Le cahier des charges
(§16 ter) l'impose : « suppression du fichier depose aussitot l'analyse
de conformite terminee ». Un fichier de statuts porte des noms, des
adresses et des montants — le conserver serait une prise de risque
gratuite, et une promesse rompue.

Rien n'est stocke non plus du rapport : il est rendu, affiche, et c'est
tout. L'utilisateur le garde s'il le veut.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependances import utilisateur_courant
from app.models import Utilisateur
from app.schemas import RapportConformite
from app.services.conformite import (
    DocumentRefuse,
    analyser,
    extraire_texte,
    mentions_obligatoires,
    resumer,
)

journal = logging.getLogger(__name__)

routeur = APIRouter(tags=["conformite"])

# Les modeles disponibles, et l'article du corpus qui porte leurs
# mentions obligatoires. LA GRILLE N'EST PAS ICI : elle est lue dans
# l'article au moment de l'analyse, si bien qu'une revision du texte la
# met a jour toute seule.
MODELES = {
    "statuts_societe": {
        "libelle": "Statuts de société commerciale",
        "sigle": "AUSCGIE",
        "numero": "13",
    },
    "statuts_sa": {
        "libelle": "Statuts de société anonyme",
        "sigle": "AUSCGIE",
        "numero": "397",
    },
    "statuts_cooperative": {
        "libelle": "Statuts de société coopérative",
        "sigle": "AUSCOOP",
        "numero": "18",
    },
}


@routeur.get("/conformite/modeles")
def lister_modeles() -> list[dict]:
    """Les types de documents analysables, avec leur base légale."""
    return [
        {
            "cle": cle,
            "libelle": modele["libelle"],
            "sigle": modele["sigle"],
            "numero": modele["numero"],
        }
        for cle, modele in MODELES.items()
    ]


@routeur.post("/conformite/analyser")
async def analyser_document(
    fichier: UploadFile = File(...),
    modele: str = Form("statuts_societe"),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> RapportConformite:
    """Confronte un document aux mentions obligatoires de son modèle.

    OBLIGATION DE MOYENS, JAMAIS DE RÉSULTAT. Le rapport dit ce qui a été
    vu, point par point, avec l'article qui le fonde. Il ne garantit
    aucune conformité — le cahier des charges range explicitement cette
    garantie hors périmètre (§3).
    """
    if modele not in MODELES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Modèle inconnu. Valeurs acceptées : {', '.join(MODELES)}.",
        )
    reference = MODELES[modele]

    # La grille est lue DANS LE CORPUS, à chaque analyse.
    article = db.execute(
        text(
            "SELECT a.id, a.numero, a.contenu, t.sigle, t.version "
            "FROM article a JOIN texte t ON t.id = a.texte_id "
            "WHERE t.sigle = :sigle AND a.numero = :numero "
            "  AND a.date_abrogation IS NULL LIMIT 1"
        ),
        {"sigle": reference["sigle"], "numero": reference["numero"]},
    ).mappings().first()

    if article is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"L'article {reference['sigle']} {reference['numero']}, qui porte "
            "les mentions obligatoires de ce modèle, n'est pas dans le corpus. "
            "L'analyse ne peut pas être fondée.",
        )

    contenu = await fichier.read()
    try:
        texte_document = extraire_texte(contenu, fichier.filename or "document.pdf")
    except DocumentRefuse as erreur:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(erreur)
        ) from erreur
    finally:
        # Le contenu ne survit pas a la requete. Rien n'a ete ecrit sur
        # le disque a aucun moment.
        contenu = b""

    points = mentions_obligatoires(article["contenu"])
    if not points:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Aucune mention obligatoire n'a pu être lue dans l'article de "
            "référence : l'analyse serait sans base.",
        )

    rapport = analyser(texte_document, points)
    journal.info(
        "Conformite %s analysee pour %s : %s point(s).",
        modele,
        utilisateur.email,
        len(rapport),
    )

    return RapportConformite(
        modele=reference["libelle"],
        article_id=article["id"],
        sigle=article["sigle"],
        numero=article["numero"],
        version_corpus=article["version"],
        points=rapport,
        compte=resumer(rapport),
    )
