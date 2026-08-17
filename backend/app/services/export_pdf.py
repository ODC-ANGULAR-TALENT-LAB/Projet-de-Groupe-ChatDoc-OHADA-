"""Export PDF d'une reponse sourcee.

A QUOI CA SERT VRAIMENT. L'expert-comptable ne consulte pas pour le
plaisir : il joint la reponse a une note de travail, a un dossier client,
parfois a une justification devant l'administration. Le cahier des
charges en fait un besoin explicite (§6) et une user story (§14).

TROIS REGLES, TOUTES DEDUITES DU §16 TER.

1. L'AVERTISSEMENT SUIT LE DOCUMENT. « Rappel repris dans chaque export
   PDF » : un PDF qui circule sans lui, detache de l'interface qui le
   portait, est exactement le scenario ou un lecteur prend une aide
   documentaire pour un avis juridique.
2. LA VERSION DU CORPUS EST IMPRIMEE. Une reponse exacte aujourd'hui
   sera fausse apres la prochaine loi de finances. Le lecteur doit
   pouvoir dater ce qu'il lit — c'est aussi ce qui permet de reconstituer
   sur quelle base l'application a repondu.
3. L'EXTRAIT OFFICIEL FIGURE EN ENTIER. C'est la piece justificative ;
   un export qui ne porterait que la synthese perdrait ce qui fait la
   valeur du produit.
"""

from __future__ import annotations

import datetime
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.services.decoupage import DEBUT_ZONE_PRIVEE, FIN_ZONE_PRIVEE

BLEU_NUIT = colors.HexColor("#1B2A4A")
OR = colors.HexColor("#C9A227")
GRIS = colors.HexColor("#5F5F5F")

AVERTISSEMENT = (
    "ChatDocs OHADA est une aide a la recherche documentaire. Ce document "
    "ne constitue ni une consultation juridique, ni un conseil fiscal, ni "
    "un acte relevant d'une profession reglementee. L'extrait officiel est "
    "reproduit precisement pour que vous exerciez votre propre controle "
    "professionnel."
)


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle(
            "titre",
            parent=base["Title"],
            fontName="Times-Bold",
            fontSize=16,
            textColor=BLEU_NUIT,
            spaceAfter=2 * mm,
        ),
        "meta": ParagraphStyle(
            "meta", parent=base["Normal"], fontSize=8, textColor=GRIS, spaceAfter=1 * mm
        ),
        "question": ParagraphStyle(
            "question",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=BLEU_NUIT,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "corps": ParagraphStyle(
            "corps",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
            alignment=TA_JUSTIFY,
            spaceAfter=2 * mm,
        ),
        "etiquette": ParagraphStyle(
            "etiquette",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            textColor=OR,
            spaceBefore=4 * mm,
            spaceAfter=1 * mm,
        ),
        "reference": ParagraphStyle(
            "reference",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=12,
            textColor=BLEU_NUIT,
            spaceAfter=1 * mm,
        ),
        # L'extrait officiel : en serif et en retrait, pour qu'on ne le
        # confonde jamais avec le commentaire de l'assistant.
        "extrait": ParagraphStyle(
            "extrait",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=10,
            leading=15,
            leftIndent=6 * mm,
            alignment=TA_JUSTIFY,
            spaceAfter=2 * mm,
        ),
        "avertissement": ParagraphStyle(
            "avertissement",
            parent=base["Normal"],
            fontSize=7.5,
            leading=11,
            textColor=GRIS,
            spaceBefore=3 * mm,
        ),
    }


def _echapper(texte: str) -> str:
    """Prepare un texte pour ReportLab.

    DEUX NEUTRALISATIONS, POUR DEUX RAISONS DIFFERENTES.

    1. ReportLab interprete un balisage : « < » et « & » viennent du
       modele ou du corpus, et un article fiscal qui compare des seuils
       en contient.

    2. Les glyphes de police symbolique (zone privee Unicode) n'ont
       aucune correspondance dans les polices du PDF : ReportLab les rend
       en caracteres arbitraires. Constate sur l'export reel d'une
       reponse citant l'AUDCG : « categories suivantes : nn 1° locaux »,
       ou « nn » remplacait deux puces.

       Le defaut se corrige a l'ingestion (voir decoupage.normaliser),
       mais un PDF CIRCULE : il finit dans un dossier client, parfois
       transmis a un tiers. On ne laisse pas un artefact sortir dans une
       piece qui echappe ensuite a l'application, meme si le corpus
       amont est cense etre propre.
    """
    propre = "".join(
        " " if DEBUT_ZONE_PRIVEE <= ord(c) <= FIN_ZONE_PRIVEE else c
        for c in (texte or "")
    )
    return propre.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def construire(
    question: str,
    reponse: str,
    citations: list[dict],
    versions_corpus: list[str],
    genere_le: datetime.date | None = None,
) -> bytes:
    """Rend le PDF d'un echange, en octets."""
    style = _styles()
    tampon = io.BytesIO()
    document = SimpleDocTemplate(
        tampon,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title="ChatDocs OHADA — reponse sourcee",
    )

    date = genere_le or datetime.date.today()
    elements = [
        Paragraph("ChatDocs OHADA", style["titre"]),
        Paragraph(
            f"Reponse sourcee — editee le {date:%d/%m/%Y}", style["meta"]
        ),
    ]
    if versions_corpus:
        elements.append(
            Paragraph(
                "Corpus utilise : " + _echapper(", ".join(versions_corpus)),
                style["meta"],
            )
        )
    elements += [
        Spacer(1, 3 * mm),
        HRFlowable(width="100%", color=OR, thickness=1.2),
        Paragraph(_echapper(question), style["question"]),
    ]

    for paragraphe in (reponse or "").split("\n"):
        if paragraphe.strip():
            elements.append(Paragraph(_echapper(paragraphe), style["corps"]))

    for citation in citations:
        elements.append(Paragraph("BASE LEGALE", style["etiquette"]))
        elements.append(
            Paragraph(
                f"Article {_echapper(citation['numero'])} de l'"
                f"{_echapper(citation['sigle'])}",
                style["reference"],
            )
        )
        if citation.get("chemin"):
            elements.append(Paragraph(_echapper(citation["chemin"]), style["meta"]))
        elements.append(
            Paragraph("« " + _echapper(citation["extrait"]) + " »", style["extrait"])
        )

    elements += [
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", color=colors.HexColor("#E2DED2"), thickness=0.8),
        Paragraph(AVERTISSEMENT, style["avertissement"]),
    ]

    document.build(elements)
    return tampon.getvalue()
