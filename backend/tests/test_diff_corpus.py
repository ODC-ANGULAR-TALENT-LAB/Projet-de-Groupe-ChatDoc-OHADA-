"""Tests du diff entre un depot et le corpus en vigueur.

C'est ce diff qui decide de ce que le juriste relit. S'il classe mal,
soit on lui fait relire 400 articles au lieu de 30 — et il ne le fera
pas —, soit on laisse passer une modification sans relecture. Les deux
sont graves, le second l'est davantage.
"""

from __future__ import annotations

from app.services.diff_corpus import (
    ABROGE,
    AJOUTE,
    INCHANGE,
    MODIFIE,
    a_relire,
    comparer,
    normaliser_comparaison,
    resumer,
)


def depose(numero: str, contenu: str, chemin: str = "Livre I") -> dict:
    return {"numero": numero, "contenu": contenu, "chemin": chemin}


def en_base(article_id: int, numero: str, contenu: str) -> dict:
    return {
        "id": article_id,
        "numero": numero,
        "contenu": contenu,
        "chemin": "Livre I",
    }


def par_numero(analyse: list[dict], numero: str) -> dict:
    return next(entree for entree in analyse if entree["numero"] == numero)


def test_les_quatre_statuts_sont_atteints():
    analyse = comparer(
        [
            depose("1", "Le capital social est librement fixe."),
            depose("2", "Le nouveau texte de l'article deux."),
            depose("4", "Un article qui n'existait pas."),
        ],
        [
            en_base(10, "1", "Le capital social est librement fixe."),
            en_base(11, "2", "L'ancien texte de l'article deux."),
            en_base(12, "3", "Un article retire de la revision."),
        ],
    )

    assert par_numero(analyse, "1")["statut"] == INCHANGE
    assert par_numero(analyse, "2")["statut"] == MODIFIE
    assert par_numero(analyse, "3")["statut"] == ABROGE
    assert par_numero(analyse, "4")["statut"] == AJOUTE


def test_l_article_disparu_est_signale_comme_abroge():
    """Le cas le plus facile a manquer, et le plus lourd.

    Un article qui n'est plus dans la nouvelle version mais resterait
    interrogeable ferait citer du droit qui n'existe plus.
    """
    analyse = comparer([], [en_base(12, "3", "Texte supprime par la revision.")])

    abroge = par_numero(analyse, "3")
    assert abroge["statut"] == ABROGE
    assert abroge["article_id"] == 12
    assert abroge["nouveau"] is None
    # L'ancien texte reste disponible : le juriste doit voir ce qu'il abroge.
    assert "supprime" in abroge["ancien"]


def test_la_typographie_ne_fait_pas_une_modification():
    """Apostrophes courbes, tirets typographiques, accents, espaces.

    Deux editions du meme texte n'emploient pas la meme ponctuation.
    Sans neutralisation, tout le texte ressort « modifie » et le diff ne
    sert plus a rien : la vraie modification se noie dans le bruit.
    """
    analyse = comparer(
        [depose("1", "L’associe   cede ses parts — sous conditions.")],
        [en_base(10, "1", "L'associé cède ses parts - sous conditions.")],
    )

    assert par_numero(analyse, "1")["statut"] == INCHANGE


def test_une_virgule_en_plus_reste_une_modification():
    """Le garde-fou de la regle precedente.

    On neutralise la FORME, jamais le fond : un mot ajoute ou retire
    change le droit, si petit soit-il.
    """
    analyse = comparer(
        [depose("1", "Le delai est de quinze jours ouvrables.")],
        [en_base(10, "1", "Le delai est de quinze jours.")],
    )

    assert par_numero(analyse, "1")["statut"] == MODIFIE


def test_le_contenu_original_n_est_jamais_altere():
    """La normalisation sert a COMPARER, pas a stocker.

    Le contenu rendu est le texte officiel, accents et apostrophes
    compris : c'est lui qui sera montre a l'utilisateur comme preuve.
    """
    officiel = "L’associé cède ses parts."
    analyse = comparer([depose("1", officiel)], [])

    assert par_numero(analyse, "1")["nouveau"] == officiel
    assert normaliser_comparaison(officiel) != officiel


def test_seuls_les_articles_a_decider_sont_a_relire():
    """L'apport central du diff : ne pas faire relire l'inchange."""
    analyse = comparer(
        [depose(str(n), f"Texte {n}") for n in range(1, 51)],
        [en_base(n, str(n), f"Texte {n}") for n in range(1, 50)],
    )

    assert resumer(analyse)[INCHANGE] == 49
    # Un seul article demande une decision : le cinquantieme, ajoute.
    assert [entree["numero"] for entree in a_relire(analyse)] == ["50"]


def test_similarite_bornee_et_ordonnable():
    analyse = comparer(
        [
            depose("1", "un texte totalement different sans aucun rapport"),
            depose("2", "le delai est de quinze jours ouvrables"),
        ],
        [
            en_base(10, "1", "le capital social est librement fixe par les statuts"),
            en_base(11, "2", "le delai est de quinze jours"),
        ],
    )

    tres_change = par_numero(analyse, "1")["similarite"]
    peu_change = par_numero(analyse, "2")["similarite"]

    assert 0.0 <= tres_change <= 1.0
    assert 0.0 <= peu_change <= 1.0
    # Le juriste doit pouvoir trier : ce qui a le plus bouge en premier.
    assert tres_change < peu_change
