"""Tests de la fusion des resultats de recherche (C.2).

La fusion et le seuil de refus sont deux des quatre points que le
document d'architecture designe comme devant etre couverts par des tests
unitaires : c'est la que se joue la promesse du produit.

Les requetes SQL elles-memes ne sont pas testees ici - elles exigent une
base peuplee, ce qui releve des tests d'integration (phase E).
"""

from __future__ import annotations

from conftest import article

from app.services.recherche import K_RRF, fusion_rrf, pertinence


def test_article_present_dans_les_deux_listes_passe_devant():
    """Tout l'interet de la fusion : ce qui est trouve par les deux
    methodes est plus surement pertinent que ce qui n'est trouve que par
    une seule."""
    vect = [article(1, "10", score_vectoriel=0.7), article(2, "20", score_vectoriel=0.6)]
    lex = [article(3, "30", score_lexical=0.9), article(1, "10", score_lexical=0.4)]

    resultats = fusion_rrf(vect, lex)

    assert resultats[0][0]["id"] == 1


def test_les_deux_scores_bruts_sont_conserves():
    """Le defaut du code du guide : un dictionnaire construit sur la
    concatenation des deux listes ecrase l'entree vectorielle par
    l'entree lexicale, et perd le score qui sert ensuite a decider du
    refus."""
    vect = [article(1, "10", score_vectoriel=0.77)]
    lex = [article(1, "10", score_lexical=0.42)]

    fusionne = fusion_rrf(vect, lex)[0][0]

    assert fusionne["score_vectoriel"] == 0.77
    assert fusionne["score_lexical"] == 0.42


def test_score_absent_vaut_zero():
    """Un article trouve par une seule des deux methodes doit quand meme
    porter les deux champs, sinon le calcul du seuil plante."""
    fusionne = fusion_rrf([article(1, "10", score_vectoriel=0.7)], [])[0][0]

    assert fusionne["score_lexical"] == 0.0


def test_le_score_rrf_ne_depend_que_du_rang():
    """Deux listes, rang 1 dans chacune : le maximum theorique."""
    vect = [article(1, "10", score_vectoriel=0.01)]
    lex = [article(1, "10", score_lexical=0.01)]

    _, score = fusion_rrf(vect, lex)[0]

    assert score == 2.0 / (K_RRF + 1)


def test_le_score_rrf_ne_peut_pas_atteindre_le_seuil_du_guide():
    """Le maximum theorique du score RRF vaut environ 0,033, tres en
    dessous de SEUIL_PERTINENCE=0,55. Comparer l'un a l'autre - ce que
    fait le guide - ferait refuser toutes les questions."""
    maximum_theorique = 2.0 / (K_RRF + 1)

    assert maximum_theorique < 0.05


def test_nombre_de_resultats_limite():
    vect = [article(n, str(n), score_vectoriel=0.5) for n in range(1, 21)]

    assert len(fusion_rrf(vect, [], n=8)) == 8


def test_resultats_ordonnes_du_meilleur_au_moins_bon():
    vect = [article(n, str(n), score_vectoriel=0.5) for n in range(1, 6)]
    lex = [article(n, str(n), score_lexical=0.5) for n in range(5, 0, -1)]

    scores = [score for _, score in fusion_rrf(vect, lex)]

    assert scores == sorted(scores, reverse=True)


def test_listes_vides_ne_donnent_rien():
    assert fusion_rrf([], []) == []


def test_pertinence_retient_le_meilleur_score_vectoriel():
    """La pertinence est une similarite cosinus, entre 0 et 1 : c'est
    elle qu'on compare au seuil, pas le score de classement."""
    resultats = [
        (article(1, "10", score_vectoriel=0.42), 0.03),
        (article(2, "20", score_vectoriel=0.81), 0.02),
    ]

    assert pertinence(resultats) == 0.81


def test_pertinence_nulle_sans_resultat():
    """Aucun resultat doit conduire au refus, pas a une erreur."""
    assert pertinence([]) == 0.0
