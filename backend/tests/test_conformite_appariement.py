"""L'appariement des points de conformite au rapport rendu.

CE QUI SE PASSAIT. La liste envoyee au modele s'ecrivait
« 1° la forme de la societe » — repere et libelle sur la meme ligne,
sans separation. Le modele renvoyait donc la LIGNE ENTIERE comme repere,
l'appariement par dictionnaire echouait sur les treize points, et le
rapport affichait « Non verifie. » partout.

LA FONCTIONNALITE ETAIT ENTIEREMENT INOPERANTE, tout en repondant
HTTP 200 avec un rapport d'apparence normale. Rien ne distinguait « le
modele n'a pas su conclure » de « le code n'a pas su lire sa reponse ».

Mesure sur un projet de statuts reel : 13 points « a verifier » avant,
7 conformes et 6 ecarts apres.
"""

import pytest

from app.services.conformite import _cle, _indexer


@pytest.mark.parametrize(
    "recu, attendu",
    [
        ("1°", "1"),
        ("[1°]", "1"),
        # La forme qui a casse la fonctionnalite : la ligne entiere.
        ("1° la forme de la société", "1"),
        ("  10°  ", "10"),
        ("[13°] les modalités de son fonctionnement", "13"),
        ("13", "13"),
    ],
)
def test_toutes_les_variantes_convergent(recu, attendu):
    """ON N'EXIGE PAS DU MODELE UNE CHAINE EXACTE.

    Meme avec un format demande sans ambiguite, il ecrira tantot « 1° »,
    tantot « [1°] », tantot la ligne entiere. Exiger l'egalite stricte a
    rendu la fonctionnalite muette.
    """
    assert _cle(recu) == attendu


def test_un_repere_non_numerique_est_conserve_tel_quel():
    """Aucune perte silencieuse si la grille change de numerotation."""
    assert _cle("P3") == "P3"


def test_l_index_apparie_malgre_le_libelle_recopie():
    rendus = [
        {"repere": "1° la forme de la société", "statut": "conforme", "constat": "vu"},
        {"repere": "[2°]", "statut": "ecart", "constat": "absent"},
    ]
    index = _indexer(rendus)

    assert index["1"]["statut"] == "conforme"
    assert index["2"]["statut"] == "ecart"


def test_la_premiere_reponse_gagne():
    """Si le modele repond deux fois pour un point, la seconde n'ecrase pas.

    Sans cela, une reponse contradictoire remplacerait silencieusement la
    premiere, et le rapport dependrait de l'ordre d'emission.
    """
    index = _indexer(
        [
            {"repere": "1°", "statut": "conforme", "constat": "PREMIERE"},
            {"repere": "1° la forme", "statut": "ecart", "constat": "seconde"},
        ]
    )
    assert index["1"]["constat"] == "PREMIERE"
