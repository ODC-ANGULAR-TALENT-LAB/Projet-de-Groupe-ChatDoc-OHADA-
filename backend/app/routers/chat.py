"""E.4 - Le coeur du produit : question -> reponse sourcee.

Plus l'historique des conversations, qui en est la trace.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependances import utilisateur_courant
from app.models import (
    Article,
    Citation,
    Conversation,
    Message,
    Signalement,
    Utilisateur,
)
from app.schemas import (
    CitationSortie,
    ConversationDetail,
    ConversationSortie,
    MessageSortie,
    QuestionEntree,
    ReponseChat,
    SignalementEntree,
)
from app.services.export_pdf import construire as construire_pdf
from app.services.rag import ServiceIndisponible, repondre, repondre_en_flux

routeur = APIRouter(tags=["chat"])

LONGUEUR_TITRE = 80

# Tours remontes pour comprendre une question de suivi. Six couvre trois
# echanges : au-dela, le fil n'eclaire plus la question courante.
TOURS_HISTORIQUE = 6


def _sse(charge: dict) -> str:
    """Un evenement Server-Sent Events.

    ensure_ascii=False : le JSON part en UTF-8, sans quoi chaque accent
    d'un texte juridique francais couterait six caracteres.
    """
    return "data: " + json.dumps(charge, ensure_ascii=False) + "\n\n"


def _conversation(
    db: Session, utilisateur: Utilisateur, conversation_id: int | None, question: str
) -> Conversation:
    """Reprend la conversation demandee, ou en ouvre une nouvelle."""
    if conversation_id is not None:
        conversation = db.get(Conversation, conversation_id)
        # Cloisonnement : on ne reprend que ses propres conversations.
        if conversation is None or conversation.utilisateur_id != utilisateur.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable")
        return conversation

    conversation = Conversation(
        utilisateur_id=utilisateur.id, titre=question[:LONGUEUR_TITRE]
    )
    db.add(conversation)
    db.flush()
    return conversation


def _historique(db: Session, conversation: Conversation) -> list[dict]:
    """Les tours precedents du fil, du plus ancien au plus recent.

    C'est ce qui manquait pour que « et pour une SA ? » fonctionne : sans
    fil, cette question part seule a la recherche vectorielle et ne
    ressemble a aucun article. Voir app/services/reformulation.py.

    On ne remonte que les derniers tours : au-dela, ils n'aident plus a
    comprendre la question courante et alourdissent chaque appel.
    """
    if conversation.id is None:
        return []

    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(TOURS_HISTORIQUE)
    ).all()
    return [
        {"role": message.role, "contenu": message.contenu}
        for message in reversed(messages)
    ]


def _enregistrer(
    db: Session, conversation: Conversation, question: str, resultat: dict
) -> int:
    """Journalise l'echange et les articles cites.

    La journalisation n'est pas du confort : en cas de contestation, elle
    permet de reconstituer exactement ce que l'application a repondu, a
    quelle date, sur quelle base.
    """
    db.add(Message(conversation_id=conversation.id, role="user", contenu=question))

    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        contenu=resultat["reponse"],
    )
    db.add(message)
    db.flush()

    for citation in resultat["citations"]:
        db.add(
            Citation(
                message_id=message.id,
                article_id=citation["article_id"],
                extrait=citation["extrait"],
            )
        )

    # L'identifiant remonte au frontend : c'est lui que visent l'export
    # PDF et le signalement.
    return message.id


@routeur.post("/chat/question")
def poser_question(
    corps: QuestionEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> ReponseChat:
    if utilisateur.quota_restant <= 0:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED, "Quota mensuel epuise"
        )

    conversation = _conversation(db, utilisateur, corps.conversation_id, corps.question)

    try:
        resultat = repondre(
            corps.question, historique=_historique(db, conversation)
        )
    except ServiceIndisponible as erreur:
        # Une panne n'est pas un refus : on le dit, et le quota n'est
        # evidemment pas decompte.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Le moteur de recherche est indisponible.",
        ) from erreur

    # LE QUOTA N'EST PAS DECOMPTE SUR UN REFUS. Un refus ne coute rien
    # (aucun appel LLM quand le seuil n'est pas atteint) et penaliser
    # l'utilisateur pour une question hors corpus donnerait un tres
    # mauvais signal sur une fonctionnalite qu'on revendique.
    #
    # Meme raisonnement pour une reponse sans synthese : le service de
    # redaction etait indisponible, l'utilisateur n'a pas a le payer.
    if not resultat.get("refus") and not resultat.get("sans_synthese"):
        utilisateur.quota_restant -= 1

    message_id = _enregistrer(db, conversation, corps.question, resultat)
    db.commit()

    return ReponseChat(
        **resultat, conversation_id=conversation.id, message_id=message_id
    )


@routeur.post("/chat/question/flux")
def poser_question_en_flux(
    corps: QuestionEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """La même réponse, rendue au fil de l'eau (SSE).

    Le cahier des charges (§11) demande un affichage en streaming « pour
    la perception de rapidité » : une réponse peut prendre dix secondes,
    et voir le texte se former change tout au ressenti.

    CE QUI EST DIFFUSÉ, ET CE QUI NE L'EST PAS. Seule la prose défile.
    Les citations n'arrivent que dans l'événement final, après
    validation : diffuser une référence avant de savoir si elle survivra
    au contrôle reviendrait à montrer une preuve qu'on pourrait ensuite
    retirer.

    Le point de terminaison non diffusé reste en place — c'est lui que
    joue le jeu d'évaluation, où le streaming n'apporte rien.
    """
    if utilisateur.quota_restant <= 0:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Quota mensuel epuise")

    conversation = _conversation(db, utilisateur, corps.conversation_id, corps.question)
    conversation_id = conversation.id
    historique = _historique(db, conversation)
    utilisateur_id = utilisateur.id
    db.commit()

    def evenements():
        # UNE SESSION NEUVE. Le générateur s'exécute APRÈS que la requête
        # a rendu la main : celle de la dépendance est déjà refermée, et
        # s'en servir ici lèverait une erreur au premier accès.
        from app.db import FabriqueSession

        try:
            resultat = None
            for genre, charge in repondre_en_flux(
                corps.question, historique=historique
            ):
                if genre == "texte":
                    yield _sse({"type": "texte", "texte": charge})
                else:
                    resultat = charge
        except ServiceIndisponible:
            yield _sse(
                {
                    "type": "erreur",
                    "message": "Le moteur de recherche est indisponible.",
                }
            )
            return

        if resultat is None:
            yield _sse({"type": "erreur", "message": "Aucune réponse produite."})
            return

        with FabriqueSession() as session:
            conversation_courante = session.get(Conversation, conversation_id)
            compte = session.get(Utilisateur, utilisateur_id)
            if not resultat.get("refus") and not resultat.get("sans_synthese"):
                compte.quota_restant -= 1
            message_id = _enregistrer(
                session, conversation_courante, corps.question, resultat
            )
            session.commit()

        yield _sse(
            {
                "type": "fin",
                **ReponseChat(
                    **resultat,
                    conversation_id=conversation_id,
                    message_id=message_id,
                ).model_dump(mode="json"),
            }
        )

    return StreamingResponse(
        evenements(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Sans cela, un proxy tamponne la réponse et le streaming ne
            # sert plus a rien : tout arrive d'un bloc a la fin.
            "X-Accel-Buffering": "no",
        },
    )


@routeur.get("/conversations")
def mes_conversations(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> list[ConversationSortie]:
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.utilisateur_id == utilisateur.id)
        .order_by(Conversation.cree_le.desc())
    ).all()
    return [ConversationSortie.model_validate(c) for c in conversations]


@routeur.get("/conversations/{conversation_id}")
def detail_conversation(
    conversation_id: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> ConversationDetail:
    """Détail d'une conversation, citations comprises.

    Les citations sont rechargées depuis la base à chaque relecture :
    la référence affichée reflète toujours l'article réellement cité,
    jamais une copie figée au moment de la réponse.
    """
    conversation = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(
            selectinload(Conversation.messages)
            .selectinload(Message.citations)
            .selectinload(Citation.article)
            .selectinload(Article.texte)
        )
    )
    if conversation is None or conversation.utilisateur_id != utilisateur.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable")

    return ConversationDetail(
        id=conversation.id,
        titre=conversation.titre,
        cree_le=conversation.cree_le,
        messages=[
            MessageSortie(
                id=message.id,
                role=message.role,
                contenu=message.contenu,
                cree_le=message.cree_le,
                citations=[
                    CitationSortie(
                        article_id=citation.article.id,
                        sigle=citation.article.texte.sigle,
                        numero=citation.article.numero,
                        chemin=citation.article.chemin,
                        extrait=citation.extrait or "",
                    )
                    for citation in message.citations
                ],
            )
            for message in conversation.messages
        ],
    )


def _message_de_l_utilisateur(
    db: Session, message_id: int, utilisateur: Utilisateur
) -> Message:
    """Le message demandé, s'il appartient bien à celui qui le demande."""
    message = db.scalar(
        select(Message)
        .where(Message.id == message_id)
        .options(
            selectinload(Message.conversation),
            selectinload(Message.citations)
            .selectinload(Citation.article)
            .selectinload(Article.texte),
        )
    )
    if (
        message is None
        or message.conversation is None
        or message.conversation.utilisateur_id != utilisateur.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message introuvable")
    return message


@routeur.get("/messages/{message_id}/export")
def exporter_reponse(
    message_id: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> Response:
    """Le PDF d'une réponse sourcée, à joindre à une note de travail.

    L'export reprend l'avertissement déontologique et la version des
    textes cités : un PDF circule détaché de l'interface qui le portait,
    et c'est précisément le scénario où un lecteur prendrait une aide
    documentaire pour un avis juridique (§16 ter).
    """
    message = _message_de_l_utilisateur(db, message_id, utilisateur)
    if message.role != "assistant":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Seule une réponse de l'assistant s'exporte.",
        )

    # La question est le message qui précède immédiatement la réponse.
    question = db.scalar(
        select(Message.contenu)
        .where(
            Message.conversation_id == message.conversation_id,
            Message.id < message.id,
            Message.role == "user",
        )
        .order_by(Message.id.desc())
        .limit(1)
    )

    citations = [
        {
            "sigle": citation.article.texte.sigle,
            "numero": citation.article.numero,
            "chemin": citation.article.chemin,
            "extrait": citation.extrait or citation.article.contenu,
        }
        for citation in message.citations
    ]
    versions = sorted(
        {
            f"{c.article.texte.sigle} ({c.article.texte.version}, consolidé au "
            f"{c.article.texte.date_consolidation:%d/%m/%Y})"
            for c in message.citations
        }
    )

    pdf = construire_pdf(
        question=question or "(question non retrouvée)",
        reponse=message.contenu,
        citations=citations,
        versions_corpus=versions,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="chatdocs-reponse-{message_id}.pdf"'
            )
        },
    )


@routeur.post("/signalements", status_code=status.HTTP_201_CREATED)
def signaler(
    corps: SignalementEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> dict:
    """Enregistre une réponse contestée.

    Le registre des incidents est un dispositif de PROTECTION (§16 ter),
    au même titre que les conditions d'utilisation : il démontre la
    diligence de l'éditeur en cas de litige. Il n'a de valeur que s'il
    est tenu depuis le début — ouvert le jour du premier litige, il ne
    prouve rien.
    """
    message = _message_de_l_utilisateur(db, corps.message_id, utilisateur)

    signalement = Signalement(
        message_id=message.id,
        utilisateur_id=utilisateur.id,
        motif=corps.motif,
        commentaire=corps.commentaire,
    )
    db.add(signalement)
    db.commit()

    return {
        "enregistre": True,
        "message": "Signalement enregistré. Il sera examiné et corrigé si nécessaire.",
    }


@routeur.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def effacer_conversation(
    conversation_id: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> None:
    """Effacement a la demande - engagement de confidentialite.

    Le contenu des questions n'est pas exploite au-dela de l'historique
    visible par l'utilisateur ; il doit pouvoir le supprimer.
    """
    conversation = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    if conversation is None or conversation.utilisateur_id != utilisateur.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable")

    for message in conversation.messages:
        db.query(Citation).filter(Citation.message_id == message.id).delete()
        db.delete(message)
    db.delete(conversation)
    db.commit()
