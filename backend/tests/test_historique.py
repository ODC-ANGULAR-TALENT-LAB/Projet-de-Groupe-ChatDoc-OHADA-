"""Tests de la restitution des citations dans l'historique.

Une conversation reprise doit garder ses blocs « Base légale ». Sans
eux, un échange relu perd exactement ce qui le rendait vérifiable, et
l'historique ne vaut pas mieux que celui d'un chat généraliste.

Ces tests vérifient la conversion modèle -> schéma sans base : le
parcours complet contre PostgreSQL relève des tests d'intégration.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from app.schemas import CitationSortie, ConversationDetail, MessageSortie


def citation(article_id: int, numero: str) -> CitationSortie:
    return CitationSortie(
        article_id=article_id,
        sigle="AUSCGIE",
        numero=numero,
        chemin="Livre II - De la SARL",
        extrait="Les associes sont convoques quinze jours au moins avant.",
    )


def test_un_message_porte_ses_citations():
    message = MessageSortie(
        id=1,
        role="assistant",
        contenu="Le delai est de quinze jours.",
        cree_le=datetime.datetime.now(datetime.timezone.utc),
        citations=[citation(10, "337")],
    )

    assert len(message.citations) == 1
    assert message.citations[0].numero == "337"


def test_un_message_sans_citation_reste_valide():
    """Un refus journalisé n'a pas de citation : le champ doit être
    optionnel, sinon relire un refus ferait échouer la sérialisation."""
    message = MessageSortie(
        id=2,
        role="assistant",
        contenu="Cette question depasse les textes disponibles.",
        cree_le=datetime.datetime.now(datetime.timezone.utc),
    )

    assert message.citations == []


def test_une_conversation_reprise_conserve_l_ordre():
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    detail = ConversationDetail(
        id=1,
        titre="Delai de convocation",
        cree_le=maintenant,
        messages=[
            MessageSortie(id=1, role="user", contenu="Quel delai ?", cree_le=maintenant),
            MessageSortie(
                id=2,
                role="assistant",
                contenu="Quinze jours.",
                cree_le=maintenant,
                citations=[citation(10, "337")],
            ),
        ],
    )

    assert [m.role for m in detail.messages] == ["user", "assistant"]
    assert detail.messages[0].citations == []
    assert detail.messages[1].citations[0].article_id == 10


def test_la_reference_vient_de_l_article_pas_de_la_citation():
    """Le sigle, le numéro et le chemin sont relus en base à chaque
    consultation. Une référence figée au moment de la réponse pourrait
    diverger de l'article réellement cité."""
    article = SimpleNamespace(
        id=10,
        numero="337",
        chemin="Livre II - De la SARL",
        texte=SimpleNamespace(sigle="AUSCGIE"),
    )
    enregistree = SimpleNamespace(article=article, extrait="quinze jours")

    sortie = CitationSortie(
        article_id=enregistree.article.id,
        sigle=enregistree.article.texte.sigle,
        numero=enregistree.article.numero,
        chemin=enregistree.article.chemin,
        extrait=enregistree.extrait or "",
    )

    assert sortie.sigle == "AUSCGIE"
    assert sortie.numero == "337"


def test_extrait_absent_devient_chaine_vide():
    """La colonne extrait est nullable en base ; le contrat d'API, lui,
    promet une chaîne."""
    enregistree = SimpleNamespace(extrait=None)

    sortie = CitationSortie(
        article_id=10,
        sigle="AUSCGIE",
        numero="337",
        chemin="Livre II",
        extrait=enregistree.extrait or "",
    )

    assert sortie.extrait == ""
