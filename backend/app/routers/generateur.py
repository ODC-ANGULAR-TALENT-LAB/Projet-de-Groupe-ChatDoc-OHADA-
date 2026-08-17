"""Generation de documents types.

LE QUESTIONNAIRE VIENT DU CORPUS. Le client demande la liste des champs
d'un modele ; le serveur lit l'article qui porte les mentions
obligatoires et la construit a partir de lui. Quand une revision change
la liste, le formulaire change avec elle.

RIEN N'EST CONSERVE. Les reponses saisies portent des noms, des adresses
et des montants — ceux d'un client. Elles servent a assembler le
document, puis la requete se termine. Aucun brouillon n'est stocke.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependances import utilisateur_courant
from app.models import Utilisateur
from app.schemas import DocumentEntree, ModeleDocument, QuestionnaireSortie
from app.services.generateur import (
    MODELES,
    assembler,
    en_docx,
    en_pdf,
    questionnaire,
)

journal = logging.getLogger(__name__)

routeur = APIRouter(tags=["generateur"])

TYPE_DOCX = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _article_de_reference(db: Session, modele: dict) -> dict:
    """L'article qui porte les mentions obligatoires du modele."""
    ligne = db.execute(
        text(
            "SELECT a.contenu, t.version "
            "FROM article a JOIN texte t ON t.id = a.texte_id "
            "WHERE t.sigle = :sigle AND a.numero = :numero "
            "  AND a.date_abrogation IS NULL LIMIT 1"
        ),
        {"sigle": modele["sigle"], "numero": modele["numero"]},
    ).mappings().first()

    if ligne is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"L'article {modele['sigle']} {modele['numero']}, qui porte les "
            "mentions obligatoires de ce modèle, n'est pas dans le corpus. "
            "Le document ne peut pas être fondé.",
        )
    return dict(ligne)


def _modele(cle: str) -> dict:
    if cle not in MODELES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Modèle inconnu. Valeurs acceptées : {', '.join(MODELES)}.",
        )
    return MODELES[cle]


@routeur.get("/documents/modeles")
def lister_modeles() -> list[ModeleDocument]:
    """Les documents générables, avec leur base légale."""
    return [
        {
            "cle": cle,
            "libelle": modele["libelle"],
            "sigle": modele["sigle"],
            "numero": modele["numero"],
        }
        for cle, modele in MODELES.items()
    ]


@routeur.get("/documents/modeles/{cle}/questionnaire")
def lire_questionnaire(
    cle: str, db: Session = Depends(get_db)
) -> QuestionnaireSortie:
    """Les champs a remplir, LUS DANS L'ARTICLE de reference."""
    modele = _modele(cle)
    article = _article_de_reference(db, modele)
    champs = questionnaire(article["contenu"])

    if not champs:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Aucune mention obligatoire n'a pu être lue dans l'article de "
            "référence : le questionnaire serait sans base.",
        )

    return {
        "cle": cle,
        "libelle": modele["libelle"],
        "sigle": modele["sigle"],
        "numero": modele["numero"],
        "version_corpus": article["version"],
        "champs": champs,
    }


@routeur.post("/documents/{cle}")
def produire_document(
    cle: str,
    corps: DocumentEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> Response:
    """Assemble le document et le rend au format demande.

    LE FORMAT EST DANS L'URL DE TELECHARGEMENT, PAS DANS UNE NEGOCIATION
    DE CONTENU : le navigateur doit pouvoir enregistrer le fichier avec
    la bonne extension sans que le client ait a la deviner.
    """
    modele = _modele(cle)
    article = _article_de_reference(db, modele)
    champs = questionnaire(article["contenu"])

    document = assembler(modele, champs, corps.reponses, article["version"])

    journal.info(
        "Document %s genere pour %s : %s clause(s), %s a completer.",
        cle,
        utilisateur.email,
        len(document["clauses"]),
        document["restant_a_completer"],
    )

    if corps.format == "docx":
        return Response(
            content=en_docx(document),
            media_type=TYPE_DOCX,
            headers={
                "Content-Disposition": f'attachment; filename="{cle}.docx"'
            },
        )

    return Response(
        content=en_pdf(document),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{cle}.pdf"'},
    )
