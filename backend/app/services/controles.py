"""Controles automatiques du decoupage.

Ils detectent 90 % des erreurs de decoupage en quelques secondes, et
s'executent AVANT tout chargement en base.

COMME LE DECOUPAGE, CE MODULE EST LA SEULE IMPLEMENTATION. Les scripts
en ligne de commande et le back-office s'appuient dessus : des controles
qui divergeraient entre les deux voies d'ingestion laisseraient passer,
par l'une, ce que l'autre refuse.
"""

from __future__ import annotations

import re
from collections import Counter

# Un article plus court que cela est presque toujours un fragment de
# sommaire ou un en-tete isole.
LONGUEUR_MINIMALE = 40

# SAUF s'il est abroge. L'AUDCIF ecrit litteralement « Article 12 —
# Abroge » : six caracteres, et c'est le texte officiel exact.
#
# Un tel article DOIT entrer au corpus. Le juriste qui cherche
# l'article 12 doit apprendre qu'il est abroge, et non ne rien trouver
# — un silence serait ici la pire des reponses, et c'est precisement ce
# que ce produit existe pour eviter. Le refuser au chargement reviendrait
# a effacer du corpus une information juridique de premier ordre.
#
# On accepte aussi le libelle developpe (« Abroge par ... ») : un
# article tronque par un decoupage rate ne commence jamais par ce mot.
# UNE MENTION D'EDITION PEUT PRECEDER LE MOT. Le Code general des impots
# ecrit « Article 611 (nouveau).- Supprime. » : la parenthese signale
# que l'article a ete reecrit par une loi de finances, et elle se place
# AVANT le corps. Sans cette tolerance, l'article etait signale comme
# « trop court » — donc bloquant — alors qu'il porte exactement ce que
# le legislateur y a mis.
MARQUEUR_EDITION = r"(?:\([^)]{0,20}\)\s*)?"

RE_ABROGE = re.compile(
    rf"^\W*{MARQUEUR_EDITION}\W*(?:abrog|supprim|r[ée]serv)", re.I
)
# Un article plus long que cela est presque toujours deux articles colles.
LONGUEUR_MAXIMALE = 12000

# Part d'articles sans chemin hierarchique au-dela de laquelle on
# considere que le decoupage a echoue, et non qu'il s'agit de
# dispositions liminaires.
PART_SANS_CHEMIN_TOLEREE = 0.02

# Seuls les problemes de ce niveau empechent le chargement en base.
BLOQUANT = "bloquant"
AVERTISSEMENT = "avertissement"


# Un numero d'article, eventuellement prefixe par la lettre de son
# livre : « 18 bis », « L 6 ter », « C 149 ».
RE_NUMERO = re.compile(r"^\s*(?:([LRDC])\s*)?(\d+)", re.I)


def serie_et_numero(numero: str) -> tuple[str, int] | None:
    """Serie et partie entiere d'un numero d'article.

    « 18 bis » -> ("", 18) ; « L 6 ter » -> ("L", 6) ; « C 149 » -> ("C", 149).

    POURQUOI LA SERIE COMPTE. Le Code general des impots numerote ses
    trois livres separement : le livre premier va de 2 a 613, le livre
    deuxieme de L1 a L146, le troisieme de C1 a C149. Confondre les
    series produisait deux erreurs a la fois :

      - tous les articles L et C etaient declares « illisibles », donc
        bloquants, alors qu'ils sont parfaitement formes ;
      - la recherche de trous melangeait les trois suites, si bien que
        l'article 5 « bouchait » le trou de L5 et de C5. Elle ne
        signalait donc plus rien la ou il manquait vraiment quelque
        chose — le pire etat pour un controle.
    """
    trouve = RE_NUMERO.match(numero)
    if not trouve:
        return None
    return (trouve.group(1) or "").upper(), int(trouve.group(2))


def numero_entier(numero: str) -> int | None:
    """Partie entiere d'un numero d'article ("18 bis" -> 18)."""
    lu = serie_et_numero(numero)
    return lu[1] if lu else None


def controler(articles: list[dict]) -> list[tuple[str, str]]:
    """Renvoie la liste des problemes, chacun avec son niveau."""
    problemes: list[tuple[str, str]] = []
    numeros = [article["numero"] for article in articles]

    # a) numerotation : doublons
    doublons = sorted(
        numero for numero, compte in Counter(numeros).items() if compte > 1
    )
    if doublons:
        problemes.append(
            (
                BLOQUANT,
                f"Numeros en double ({len(doublons)}) : {doublons[:20]}"
                + (" ..." if len(doublons) > 20 else ""),
            )
        )

    # b) numerotation : trous dans la suite, SERIE PAR SERIE
    illisibles = [numero for numero in numeros if serie_et_numero(numero) is None]
    if illisibles:
        problemes.append(
            (BLOQUANT, f"Numeros illisibles : {sorted(set(illisibles))[:20]}")
        )

    par_serie: dict[str, set[int]] = {}
    for numero in numeros:
        lu = serie_et_numero(numero)
        if lu:
            par_serie.setdefault(lu[0], set()).add(lu[1])

    for serie, entiers in sorted(par_serie.items()):
        suite = sorted(entiers)
        trous = [n for n in range(suite[0], suite[-1]) if n not in entiers]
        if trous:
            etiquette = f"serie {serie} " if serie else ""
            lisibles = [f"{serie} {n}".strip() for n in trous[:20]]
            problemes.append(
                (
                    BLOQUANT,
                    f"Articles manquants ({etiquette}{len(trous)}) : {lisibles}"
                    + (" ..." if len(trous) > 20 else ""),
                )
            )

    # c) contenus vides ou aberrants
    abroges: list[str] = []
    for article in articles:
        longueur = len(article["contenu"])
        if RE_ABROGE.match(article["contenu"]):
            # Signale sans bloquer : la mention reste sous les yeux du
            # relecteur, qui doit la retrouver telle quelle dans le PDF.
            abroges.append(article["numero"])
        elif longueur < LONGUEUR_MINIMALE:
            problemes.append(
                (
                    BLOQUANT,
                    f"Article {article['numero']} trop court ({longueur} car.) "
                    f"- page {article.get('page_debut', '?')}",
                )
            )
        elif longueur > LONGUEUR_MAXIMALE:
            problemes.append(
                (
                    BLOQUANT,
                    f"Article {article['numero']} trop long ({longueur} car.) "
                    f"-> decoupage rate ? - page {article.get('page_debut', '?')}",
                )
            )
    if abroges:
        problemes.append(
            (
                AVERTISSEMENT,
                f"{len(abroges)} article(s) abroge(s), au contenu reduit a la "
                f"mention : {abroges[:12]}"
                + (" ..." if len(abroges) > 12 else "")
                + " — verifie dans le PDF que c'est bien ce qu'il porte.",
            )
        )

    # c bis) chemin hierarchique absent.
    #
    # Un texte commence souvent par des dispositions liminaires — champ
    # d'application, definitions — qui precedent le premier Livre et
    # n'ont donc aucun niveau. C'est normal et ce n'est pas un defaut.
    #
    # En revanche, si BEAUCOUP d'articles n'ont pas de chemin, c'est que
    # les expressions regulieres de niveau n'ont rien reconnu : le
    # decoupage a echoue et les articles partiront a la vectorisation
    # sans leur contexte.
    sans_chemin = [a for a in articles if not a["chemin"]]
    if sans_chemin:
        numeros = [a["numero"] for a in sans_chemin]
        detail = (
            f"{len(sans_chemin)} article(s) sans chemin hierarchique : "
            f"{numeros[:12]}" + (" ..." if len(numeros) > 12 else "")
        )
        if len(sans_chemin) > len(articles) * PART_SANS_CHEMIN_TOLEREE:
            problemes.append(
                (
                    BLOQUANT,
                    detail + " — proportion trop elevee : les niveaux "
                    "(Livre/Titre/Chapitre/Section) n'ont probablement pas "
                    "ete reconnus.",
                )
            )
        else:
            problemes.append(
                (
                    AVERTISSEMENT,
                    detail + " — normal s'il s'agit de dispositions "
                    "liminaires placees avant le premier niveau. Verifie-le "
                    "dans le PDF.",
                )
            )

    # d) signaux faibles : n'empechent pas le chargement, mais meritent un oeil
    profondeurs = {article["chemin"].count(" > ") for article in articles}
    if len(profondeurs) > 3:
        problemes.append(
            (
                AVERTISSEMENT,
                f"Profondeurs hierarchiques tres variables : {sorted(profondeurs)}",
            )
        )

    return problemes


def bloquants(problemes: list[tuple[str, str]]) -> list[str]:
    """Ne garde que les problemes qui interdisent le chargement."""
    return [message for niveau, message in problemes if niveau == BLOQUANT]
