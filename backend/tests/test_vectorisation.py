"""Tests de la preparation des embeddings (B.7).

Ce qui est teste ici est ce qui ne depend ni du reseau ni de la base :
le texte reellement envoye au fournisseur, la lecture de sa reponse, et
le format du vecteur ecrit en base. Le parcours complet jusqu'a
PostgreSQL releve des tests d'integration (phase E).
"""

from __future__ import annotations

import pytest

from app.services.embeddings import (
    extraire_vecteurs,
    formater_vecteur,
    vecteur_simule,
)

ARTICLE = {
    "id": 42,
    "sigle": "AUSCGIE",
    "numero": "337",
    "chemin": "Livre I > Titre II - Des assemblees generales",
    "contenu": "L'assemblee generale ordinaire est convoquee quinze jours avant.",
}


def test_le_chemin_hierarchique_prefixe_le_contenu(vectoriseur):
    """Un article isole est souvent incomprehensible : c'est le prefixe
    qui lui rend son sens, et la pertinence de la recherche avec."""
    resultat = vectoriseur.texte_a_vectoriser(ARTICLE)
    assert resultat.startswith(
        "AUSCGIE > Livre I > Titre II - Des assemblees generales > Article 337\n"
    )
    assert ARTICLE["contenu"] in resultat


def test_le_prefixe_precede_toujours_le_contenu(vectoriseur):
    resultat = vectoriseur.texte_a_vectoriser(ARTICLE)
    assert resultat.index("AUSCGIE") < resultat.index("assemblee generale ordinaire")


def test_vecteur_simule_deterministe():
    """Meme texte, meme vecteur : sans quoi une reprise apres
    interruption produirait un corpus incoherent, et la meme question
    ne trouverait pas les memes articles d'un appel a l'autre."""
    assert vecteur_simule("un texte", 16) == vecteur_simule("un texte", 16)


def test_vecteur_simule_change_avec_le_texte():
    assert vecteur_simule("un texte", 16) != vecteur_simule("un autre texte", 16)


def test_vecteur_simule_respecte_les_dimensions():
    assert len(vecteur_simule("un texte", 1536)) == 1536


def test_vecteur_simule_normalise():
    """Norme 1 : la distance cosinus n'a de sens que sur des vecteurs
    normalises."""
    vecteur = vecteur_simule("un texte", 64)
    norme = sum(valeur * valeur for valeur in vecteur) ** 0.5
    assert norme == pytest.approx(1.0)


def test_format_litteral_pgvector():
    assert formater_vecteur([0.5, -0.25]) == "[0.5,-0.25]"


def test_lecture_reponse_forme_data():
    reponse = {"data": [{"embedding": [1.0, 2.0]}, {"embedding": [3.0, 4.0]}]}
    assert extraire_vecteurs(reponse, 2) == [[1.0, 2.0], [3.0, 4.0]]


def test_lecture_reponse_forme_embeddings():
    assert extraire_vecteurs({"embeddings": [[1.0, 2.0]]}, 1) == [[1.0, 2.0]]


def test_reponse_incomplete_rejetee():
    """Un vecteur manquant decalerait l'appariement article/vecteur et
    attribuerait silencieusement le mauvais embedding."""
    with pytest.raises(RuntimeError, match="2 textes"):
        extraire_vecteurs({"data": [{"embedding": [1.0]}]}, 2)


def test_reponse_de_forme_inconnue_rejetee():
    with pytest.raises(RuntimeError, match="non reconnue"):
        extraire_vecteurs({"resultat": []}, 1)
