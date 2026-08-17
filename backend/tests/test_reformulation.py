"""Tests de la memoire de conversation.

Le parcours principal du cahier des charges (§9, etape 5) decrit une
question de suivi — « et pour une SA ? » — avec contexte conserve. Ces
quatre mots ne ressemblent a aucun article de loi : envoyes tels quels a
la recherche vectorielle, ils ne remontent rien. C'est cette etape qui
rend le parcours possible.
"""

from __future__ import annotations

from app.services import reformulation
from app.services.rag import construire_message_utilisateur
from app.services.reformulation import rendre_autonome

FIL = [
    {"role": "user", "contenu": "Quel est le delai de convocation d'une AG de SARL ?"},
    {"role": "assistant", "contenu": "Le delai est de quinze jours (article 337)."},
]


# ---------------------------------------------------------------------
# Reformulation
# ---------------------------------------------------------------------


def test_sans_historique_la_question_part_telle_quelle(monkeypatch):
    """Aucun appel inutile : la premiere question n'a rien a reformuler."""
    appels = []
    monkeypatch.setattr(
        reformulation, "appeler_llm", lambda **k: appels.append(k) or {}
    )

    question = "Quel est le capital minimum d'une SA ?"

    assert rendre_autonome(question, None) == question
    assert rendre_autonome(question, []) == question
    assert appels == []


def test_une_question_de_suivi_est_rendue_autonome(monkeypatch):
    from app.config import parametres

    monkeypatch.setattr(parametres, "llm_api_key", "cle-de-test")
    monkeypatch.setattr(
        reformulation,
        "appeler_llm",
        lambda **_: {
            "question": "Quel est le delai de convocation d'une AG de societe anonyme ?",
            "dependait_du_fil": True,
        },
    )

    assert "societe anonyme" in rendre_autonome("Et pour une SA ?", FIL)


def test_une_panne_retombe_sur_la_question_d_origine(monkeypatch):
    """Une reformulation ratee degraderait la recherche en silence.

    Mieux vaut chercher la question telle qu'elle a ete posee que la
    chercher deformee sans que personne ne s'en apercoive.
    """
    from app.config import parametres

    monkeypatch.setattr(parametres, "llm_api_key", "cle-de-test")
    monkeypatch.setattr(
        reformulation, "appeler_llm", lambda **_: {"question": "", "dependait_du_fil": True}
    )

    assert rendre_autonome("Et pour une SA ?", FIL) == "Et pour une SA ?"


def test_une_reformulation_aberrante_est_ecartee(monkeypatch):
    from app.config import parametres

    monkeypatch.setattr(parametres, "llm_api_key", "cle-de-test")
    monkeypatch.setattr(
        reformulation, "appeler_llm", lambda **_: {"question": "SA", "dependait_du_fil": True}
    )

    assert rendre_autonome("Et pour une SA ?", FIL) == "Et pour une SA ?"


def test_sans_fournisseur_aucune_reformulation(monkeypatch):
    from app.config import parametres

    monkeypatch.setattr(parametres, "llm_api_key", "")

    assert rendre_autonome("Et pour une SA ?", FIL) == "Et pour une SA ?"


# ---------------------------------------------------------------------
# Le fil dans le message envoye au modele
# ---------------------------------------------------------------------


def test_le_fil_est_de_la_donnee_pas_une_source():
    """Le fil aide a COMPRENDRE la question, jamais a la fonder.

    Il entre par le message utilisateur, comme les articles, et le
    message dit explicitement au modele de ne pas s'en servir pour
    repondre : la reponse ne s'appuie que sur les articles, et la
    validation des citations reste la seule garantie.
    """
    message = construire_message_utilisateur(
        "[ARTICLE id=1] AUSCGIE - Article 337\nLivre II\nLe delai est de quinze jours.",
        "Et pour une SA ?",
        FIL,
    )

    assert "FIL DE CONVERSATION" in message
    assert "PAS pour y" in message
    assert "ARTICLES DISPONIBLES" in message
    # La question reste identifiee comme telle, en fin de message.
    assert message.rstrip().endswith("QUESTION : Et pour une SA ?")


def test_sans_historique_le_message_ne_porte_pas_de_fil():
    message = construire_message_utilisateur("[ARTICLE id=1] ...", "Une question ?", None)

    assert "FIL DE CONVERSATION" not in message
