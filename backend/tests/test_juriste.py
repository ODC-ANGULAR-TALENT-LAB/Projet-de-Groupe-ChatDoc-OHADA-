"""Tests du compte juriste : droits, et frontiere avec le modele.

Deux choses sont verifiees ici, et ce sont les deux qui protegent le
corpus : qui a le droit de valider un texte, et le fait que le modele
n'a aucun pouvoir sur le classement d'un article.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.dependances import administrateur, redacteur_corpus
from app.models import Utilisateur
from app.services.analyse_depot import resumer_modifications
from app.services.diff_corpus import INCHANGE, MODIFIE


def compte(role: str) -> Utilisateur:
    utilisateur = Utilisateur()
    utilisateur.role = role
    utilisateur.email = f"{role}@exemple.test"
    return utilisateur


# ---------------------------------------------------------------------
# Qui peut quoi
# ---------------------------------------------------------------------


def test_le_juriste_redige_le_corpus():
    juriste = compte("juriste")

    assert redacteur_corpus(juriste) is juriste


def test_l_administrateur_redige_aussi_le_corpus():
    """Il serait absurde qu'un administrateur ne puisse pas depanner."""
    admin = compte("admin")

    assert redacteur_corpus(admin) is admin


def test_un_utilisateur_ordinaire_ne_redige_pas_le_corpus():
    with pytest.raises(HTTPException) as echec:
        redacteur_corpus(compte("utilisateur"))

    assert echec.value.status_code == 403


def test_le_juriste_n_attribue_pas_les_roles():
    """La separation des pouvoirs, et ce n'est pas une precaution vaine.

    Sans elle, quiconque obtient le droit de valider un texte peut se
    l'octroyer a d'autres : la chaine de responsabilite inscrite dans la
    table de provenance ne veut alors plus rien dire.
    """
    with pytest.raises(HTTPException) as echec:
        administrateur(compte("juriste"))

    assert echec.value.status_code == 403


# ---------------------------------------------------------------------
# La frontiere avec le modele
# ---------------------------------------------------------------------


def entree(numero: str, statut: str) -> dict:
    return {
        "numero": numero,
        "statut": statut,
        "article_id": 1,
        "ancien": "L'ancien texte de l'article.",
        "nouveau": "Le nouveau texte de l'article.",
        "chemin": "Livre I",
        "similarite": 0.5,
    }


def test_sans_fournisseur_le_diff_est_rendu_tel_quel(monkeypatch):
    """Le juriste ne perd qu'un confort, jamais une information.

    Si le modele est indisponible, il lit les deux textes cote a cote et
    se prononce sans lui. C'est exactement ce qui doit se produire : le
    resume est un ornement, pas un maillon de la chaine.
    """
    from app.config import parametres

    monkeypatch.setattr(parametres, "llm_api_key", "")
    analyse = [entree("1", MODIFIE), entree("2", INCHANGE)]

    rendu = resumer_modifications(analyse)

    assert [e["statut"] for e in rendu] == [MODIFIE, INCHANGE]
    assert "resume" not in rendu[0]


def test_le_modele_ne_touche_jamais_au_statut(monkeypatch):
    """LA garantie du module.

    Meme si le modele repondait n'importe quoi, le classement produit par
    la comparaison textuelle reste intact. Un modele qui pourrait
    requalifier un article en « inchange » ferait entrer une modification
    legale sans relecture — la faute que tout le produit s'interdit.
    """
    from app.config import parametres
    from app.services import analyse_depot

    monkeypatch.setattr(parametres, "llm_api_key", "cle-de-test")
    monkeypatch.setattr(
        analyse_depot,
        "appeler_llm",
        lambda **_: {"resume": "peu importe", "portee": "mineure", "statut": INCHANGE},
    )

    rendu = resumer_modifications([entree("1", MODIFIE)])

    assert rendu[0]["statut"] == MODIFIE
    assert rendu[0]["resume"] == "peu importe"


def test_les_textes_compares_restent_la_source_de_verite(monkeypatch):
    """Le resume s'ajoute, il ne remplace jamais l'ancien ni le nouveau."""
    from app.config import parametres
    from app.services import analyse_depot

    monkeypatch.setattr(parametres, "llm_api_key", "cle-de-test")
    monkeypatch.setattr(
        analyse_depot,
        "appeler_llm",
        lambda **_: {"resume": "le delai passe de 15 a 30 jours", "portee": "majeure"},
    )

    rendu = resumer_modifications([entree("1", MODIFIE)])

    assert rendu[0]["ancien"] == "L'ancien texte de l'article."
    assert rendu[0]["nouveau"] == "Le nouveau texte de l'article."
