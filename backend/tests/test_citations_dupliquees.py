"""Un article cite deux fois ne doit pas faire echouer la reponse.

CE QUI SE PASSAIT. La cle primaire de `citation` est
(message_id, article_id). Quand le modele appuyait deux affirmations
sur le MEME article — un texte qui fixe a la fois un delai et une
sanction en fonde legitimement deux — le second enregistrement violait
la contrainte, la transaction entiere echouait, et l'utilisateur
recevait 500.

La reponse etait pourtant correcte : redigee, et ses citations validees
contre le corpus. Elle etait perdue au tout dernier moment, a
l'ecriture.

CE CAS N'A RIEN DE MARGINAL. Il se produit surtout sur les questions
formulees en langage courant, ou la recherche remonte peu d'articles et
ou chacun porte plusieurs points. C'est exactement la maniere dont un
utilisateur non juriste interroge le service.
"""

from app.routers.chat import _enregistrer


class _SessionFactice:
    """Retient ce qu'on lui demande d'ecrire, sans base."""

    def __init__(self):
        self.ajoutes = []

    def add(self, objet):
        self.ajoutes.append(objet)

    def flush(self):
        # Le message doit porter un identifiant apres flush : c'est lui
        # que les citations referencent.
        for objet in self.ajoutes:
            if getattr(objet, "role", None) == "assistant" and objet.id is None:
                objet.id = 1


class _ConversationFactice:
    id = 42


def _citations_ecrites(session):
    return [o for o in session.ajoutes if type(o).__name__ == "Citation"]


def test_un_article_cite_deux_fois_n_est_ecrit_qu_une_fois():
    session = _SessionFactice()
    resultat = {
        "reponse": "Le delai est de quinze jours (art. 338).",
        "citations": [
            {"article_id": 2330, "extrait": "quinze jours au moins", "pourquoi": "delai"},
            {"article_id": 2330, "extrait": "peut etre annulee", "pourquoi": "sanction"},
            {"article_id": 2331, "extrait": "par lettre recommandee", "pourquoi": "forme"},
        ],
    }

    _enregistrer(session, _ConversationFactice(), "quel delai ?", resultat)

    ecrites = _citations_ecrites(session)
    identifiants = [c.article_id for c in ecrites]
    assert identifiants == [2330, 2331], (
        "le doublon doit etre ecarte sans perdre les autres citations"
    )


def test_la_premiere_occurrence_est_conservee():
    """C'est celle que le modele a jugee la plus directe."""
    session = _SessionFactice()
    resultat = {
        "reponse": "…",
        "citations": [
            {"article_id": 7, "extrait": "PREMIER", "pourquoi": "a"},
            {"article_id": 7, "extrait": "second", "pourquoi": "b"},
        ],
    }

    _enregistrer(session, _ConversationFactice(), "q", resultat)

    ecrites = _citations_ecrites(session)
    assert len(ecrites) == 1
    assert ecrites[0].extrait == "PREMIER"


def test_sans_citation_rien_n_est_ecrit():
    """Un refus n'a pas de citation, et cela reste un cas nominal."""
    session = _SessionFactice()
    _enregistrer(
        session,
        _ConversationFactice(),
        "q",
        {"reponse": "Je ne peux pas repondre.", "citations": []},
    )
    assert _citations_ecrites(session) == []
