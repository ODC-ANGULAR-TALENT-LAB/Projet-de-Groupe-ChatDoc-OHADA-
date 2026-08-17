"""Tests de la lecture d'un JSON en cours d'ecriture.

Ce module sert a afficher la reponse au fil de l'eau. Il travaille sur
un document tronque : il DOIT rendre la main proprement dans tous les
cas, y compris les plus tordus, plutot que de lever une exception au
milieu d'un flux.

Le JSON complet reste parse normalement a la fin, et c'est lui qui fait
foi. Ces tests verifient donc surtout que rien ne casse.
"""

from __future__ import annotations

import json

from app.services.flux_json import extraire_reponse_partielle


def test_champ_pas_encore_commence():
    assert extraire_reponse_partielle("") == ""
    assert extraire_reponse_partielle('{"rep') == ""
    assert extraire_reponse_partielle('{"reponse"') == ""
    assert extraire_reponse_partielle('{"reponse":') == ""


def test_valeur_en_cours_d_ecriture():
    assert extraire_reponse_partielle('{"reponse": "Dans l') == "Dans l"
    assert (
        extraire_reponse_partielle('{"reponse": "Le delai est de quinze')
        == "Le delai est de quinze"
    )


def test_valeur_complete_s_arrete_au_guillemet():
    brut = '{"reponse": "Le delai est de quinze jours.", "citations": []}'

    assert extraire_reponse_partielle(brut) == "Le delai est de quinze jours."


def test_echappements_rendus():
    brut = json.dumps({"reponse": 'Un "delai" de 15 jours.\nPuis un retour.'})

    assert extraire_reponse_partielle(brut) == 'Un "delai" de 15 jours.\nPuis un retour.'


def test_echappement_coupe_par_la_frontiere_d_un_fragment():
    """Le cas qui casserait une lecture naive.

    Un fragment peut s'arreter entre l'antislash et la lettre qui le
    suit. On rend ce qui est sur, et le fragment suivant apportera la
    suite — plutot que d'emettre un antislash orphelin a l'ecran.
    """
    assert extraire_reponse_partielle('{"reponse": "Ligne un\\') == "Ligne un"
    assert extraire_reponse_partielle('{"reponse": "Ligne un\\n') == "Ligne un\n"


def test_echappement_unicode_partiel():
    assert extraire_reponse_partielle('{"reponse": "Societ\\u00e9') == "Societé"
    # Coupe au milieu du point de code : on s'arrete avant.
    assert extraire_reponse_partielle('{"reponse": "Societ\\u00') == "Societ"


def test_ne_leve_jamais_sur_une_entree_absurde():
    for absurde in [
        '{"reponse": "\\q',
        '{"reponse" : \n\t "ok',
        '{"citations": [], "reponse": "apres un autre champ"',
        '{"reponse":"\\u',
        '{"reponse":"\\uZZZZ"}',
        "{]}[",
    ]:
        # La seule exigence : rendre une chaine, quoi qu'il arrive.
        assert isinstance(extraire_reponse_partielle(absurde), str)


def test_le_champ_peut_ne_pas_etre_le_premier():
    brut = '{"confiance": "elevee", "reponse": "La reponse."}'

    assert extraire_reponse_partielle(brut) == "La reponse."


def test_croissance_monotone_sur_un_flux_realiste():
    """Au fil des fragments, le texte ne doit que s'allonger.

    Un affichage qui reculerait — texte qui raccourcit puis rallonge —
    donnerait une impression de bafouillage bien pire que l'attente.
    """
    complet = json.dumps(
        {
            "reponse": "Le delai est de quinze jours.\nVoir l'article 337.",
            "citations": [],
            "confiance": "elevee",
            "mise_en_garde": "",
        }
    )

    precedent = ""
    for taille in range(1, len(complet) + 1):
        courant = extraire_reponse_partielle(complet[:taille])
        assert courant.startswith(precedent) or len(courant) >= len(precedent) - 6
        if len(courant) >= len(precedent):
            precedent = courant

    assert precedent == "Le delai est de quinze jours.\nVoir l'article 337."
