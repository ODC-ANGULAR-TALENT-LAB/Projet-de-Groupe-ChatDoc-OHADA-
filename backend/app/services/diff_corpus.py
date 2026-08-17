"""Comparaison d'un depot avec le corpus deja en vigueur.

C'EST CE QUI MANQUAIT AU BACK-OFFICE. Jusqu'ici un depot ignorait
totalement ce qui etait deja en base : le juriste voyait 400 articles
sans savoir lesquels avaient bouge. Sur une revision qui en touche
trente, il devait relire les quatre cents.

Ce module repond a une seule question, article par article : par rapport
a ce qui est en vigueur aujourd'hui, celui-ci est-il AJOUTE, MODIFIE,
ABROGE, ou INCHANGE ?

AUCUN APPEL RESEAU ICI. La comparaison est purement textuelle et
deterministe : deux executions sur les memes donnees donnent le meme
resultat. Le resume en langage clair, lui, est produit ailleurs
(app/services/analyse_depot.py) et n'intervient jamais dans le
classement — un modele ne decide pas de ce qui a change.
"""

from __future__ import annotations

import re
import unicodedata

# Les quatre etats possibles d'un article dans un depot.
AJOUTE = "ajoute"
MODIFIE = "modifie"
ABROGE = "abroge"
INCHANGE = "inchange"

# Ponctuation dont la forme varie d'une edition a l'autre sans que le
# texte change : apostrophes droites ou courbes, guillemets, tirets.
# Les comparer telles quelles ferait declarer "modifie" des articles
# identiques au mot pres — et noierait les vraies modifications.
EQUIVALENCES = {
    "’": "'",  # apostrophe courbe
    "‘": "'",
    "“": '"',
    "”": '"',
    "«": '"',
    "»": '"',
    "‐": "-",
    "‑": "-",
    "–": "-",
    "—": "-",
    "−": "-",
}

RE_ESPACES = re.compile(r"\s+")


def normaliser_comparaison(texte: str) -> str:
    """Forme comparable d'un contenu d'article.

    On neutralise ce qui ne fait pas le droit : casse, accents, espaces
    multiples, ponctuation typographique. Ce qui reste — les mots et les
    chiffres — est ce sur quoi une modification se juge.

    Les accents sont retires POUR LA COMPARAISON SEULEMENT. Le contenu
    stocke, lui, n'est jamais modifie : c'est le texte officiel.
    """
    for exotique, ordinaire in EQUIVALENCES.items():
        texte = texte.replace(exotique, ordinaire)
    # Decomposition Unicode puis retrait des diacritiques.
    texte = unicodedata.normalize("NFD", texte)
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return RE_ESPACES.sub(" ", texte).strip().lower()


def _similarite(gauche: str, droite: str) -> float:
    """Part de mots communs, entre 0 et 1.

    Sert a trier l'affichage — le juriste veut voir d'abord les articles
    qui ont beaucoup bouge — jamais a decider du classement. Un article
    dont une seule virgule change reste MODIFIE.
    """
    mots_gauche = gauche.split()
    mots_droite = droite.split()
    if not mots_gauche and not mots_droite:
        return 1.0
    if not mots_gauche or not mots_droite:
        return 0.0

    # Multi-ensembles : un mot repete trois fois d'un cote et une fois de
    # l'autre ne compte qu'une correspondance.
    restants: dict[str, int] = {}
    for mot in mots_droite:
        restants[mot] = restants.get(mot, 0) + 1

    communs = 0
    for mot in mots_gauche:
        if restants.get(mot, 0) > 0:
            restants[mot] -= 1
            communs += 1

    return 2 * communs / (len(mots_gauche) + len(mots_droite))


def comparer(
    articles_deposes: list[dict], articles_en_vigueur: list[dict]
) -> list[dict]:
    """Classe chaque article du depot par rapport au corpus en vigueur.

    `articles_deposes` : ce que le decoupage a produit, avec au moins
    les cles `numero` et `contenu`.
    `articles_en_vigueur` : les articles du meme texte deja en base et
    non abroges, avec au moins `id`, `numero` et `contenu`.

    Renvoie une entree par article concerne, y compris les ABROGES —
    ceux qui existaient en base et ne figurent plus dans le depot. C'est
    le cas le plus facile a manquer, et le plus lourd de consequences :
    un article disparu qui resterait interrogeable ferait citer du droit
    qui n'existe plus.
    """
    en_vigueur = {article["numero"]: article for article in articles_en_vigueur}
    analyse: list[dict] = []
    vus: set[str] = set()

    for depose in articles_deposes:
        numero = depose["numero"]
        vus.add(numero)
        ancien = en_vigueur.get(numero)

        if ancien is None:
            analyse.append(
                {
                    "numero": numero,
                    "statut": AJOUTE,
                    "article_id": None,
                    "ancien": None,
                    "nouveau": depose["contenu"],
                    "chemin": depose.get("chemin", ""),
                    "similarite": 0.0,
                }
            )
            continue

        gauche = normaliser_comparaison(ancien["contenu"])
        droite = normaliser_comparaison(depose["contenu"])
        if gauche == droite:
            statut, similarite = INCHANGE, 1.0
        else:
            statut, similarite = MODIFIE, _similarite(gauche, droite)

        analyse.append(
            {
                "numero": numero,
                "statut": statut,
                "article_id": ancien["id"],
                "ancien": ancien["contenu"],
                "nouveau": depose["contenu"],
                "chemin": depose.get("chemin", ""),
                "similarite": round(similarite, 3),
            }
        )

    # Ce qui etait en vigueur et ne figure plus dans le depot.
    for numero, ancien in en_vigueur.items():
        if numero in vus:
            continue
        analyse.append(
            {
                "numero": numero,
                "statut": ABROGE,
                "article_id": ancien["id"],
                "ancien": ancien["contenu"],
                "nouveau": None,
                "chemin": ancien.get("chemin", ""),
                "similarite": 0.0,
            }
        )

    return analyse


def resumer(analyse: list[dict]) -> dict[str, int]:
    """Compte par statut, pour l'en-tete de l'ecran."""
    compte = {AJOUTE: 0, MODIFIE: 0, ABROGE: 0, INCHANGE: 0}
    for entree in analyse:
        compte[entree["statut"]] = compte.get(entree["statut"], 0) + 1
    return compte


def a_relire(analyse: list[dict]) -> list[dict]:
    """Les seules entrees qui demandent une decision humaine.

    Un article inchange n'a pas a etre relu : c'est precisement ce que
    le diff apporte. Sur une revision touchant trente articles, le
    juriste en relit trente, pas quatre cents.
    """
    return [entree for entree in analyse if entree["statut"] != INCHANGE]
