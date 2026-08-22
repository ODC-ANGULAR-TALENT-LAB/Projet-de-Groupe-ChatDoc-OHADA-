"""L'elargissement des termes remplace la recherche vectorielle.

LE PROBLEME QU'IL RESOUT, MESURE SUR LE CORPUS REEL. « Quel est le delai
de convocation d'une assemblee generale de SARL ? » ne remontait pas
l'article 338 de l'AUSCGIE, qui porte pourtant la reponse : l'article dit
« les associes sont convoques quinze jours au moins » et vit sous un
titre « societe a responsabilite limitee ». Le sigle « SARL » n'y figure
nulle part, et une recherche plein texte compare des chaines.

Traduire la question dans le vocabulaire du legislateur avant de
chercher fait remonter l'article. C'est ce que ces cas protegent.

CE MODULE N'AFFIRME RIEN. Il n'ameliore que ce qui est CHERCHE : le
seuil de refus, la validation des citations et la regle « aucune reponse
hors des articles fournis » restent en aval, inchanges. Un
elargissement rate degrade la recherche, il ne peut pas produire une
affirmation fausse — et ces tests verifient que toute defaillance
retombe sur la question d'origine.
"""

import pytest

from app.services import reformulation


@pytest.fixture
def sans_modele(monkeypatch):
    """Le fournisseur repond, mais on decide de quoi."""
    monkeypatch.setattr(
        reformulation.parametres, "llm_api_key", "cle-de-test", raising=False
    )
    monkeypatch.setattr(
        reformulation.parametres, "llm_modele", "modele-de-test", raising=False
    )


def _repondre(monkeypatch, charge):
    monkeypatch.setattr(
        reformulation, "appeler_llm", lambda **_: charge
    )


def test_les_termes_remplacent_la_question(sans_modele, monkeypatch):
    _repondre(
        monkeypatch,
        {"termes": "assemblee generale convocation societe responsabilite limitee"},
    )
    assert reformulation.termes_de_recherche("delai de convocation AG SARL") == (
        "assemblee generale convocation societe responsabilite limitee"
    )


def test_sans_fournisseur_la_question_passe_telle_quelle(monkeypatch):
    """Aucun appel n'est tente, et la recherche reste possible."""
    monkeypatch.setattr(reformulation.parametres, "llm_api_key", "", raising=False)

    def interdit(**_):
        raise AssertionError("aucun appel ne doit partir sans fournisseur")

    monkeypatch.setattr(reformulation, "appeler_llm", interdit)
    question = "delai de convocation AG SARL"
    assert reformulation.termes_de_recherche(question) == question


@pytest.mark.parametrize(
    "charge",
    [
        {"termes": ""},
        {"termes": "   "},
        {},
        # Trop court : l'elargissement n'a pas fait son travail.
        {"termes": "SARL"},
    ],
)
def test_une_reponse_inutilisable_retombe_sur_la_question(
    sans_modele, monkeypatch, charge
):
    """TOUTE DEFAILLANCE RETOMBE SUR LA QUESTION D'ORIGINE.

    Un elargissement rate degraderait la recherche sans que rien ne le
    signale : la question telle qu'elle a ete posee reste un point de
    depart honnete.
    """
    _repondre(monkeypatch, charge)
    question = "quel est le delai de convocation d'une AG de SARL"
    assert reformulation.termes_de_recherche(question) == question


def test_un_elargissement_qui_explose_est_ecarte(sans_modele, monkeypatch):
    """Dix fois la question : le modele a recopie autre chose."""
    _repondre(monkeypatch, {"termes": "mot " * 500})
    question = "delai de convocation AG SARL"
    assert reformulation.termes_de_recherche(question) == question
