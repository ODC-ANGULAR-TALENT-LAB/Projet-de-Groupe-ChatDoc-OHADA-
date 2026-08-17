"""B.4 et B.5 - Controles automatiques et echantillon de relecture.

Ces controles detectent 90 % des erreurs de decoupage en quelques
secondes. Ils se lancent AVANT de charger quoi que ce soit en base.

    python ingestion/controler.py ingestion/sortie/auscgie_2014.articles.json
    python ingestion/controler.py ... --echantillon 20

Code de retour : 0 si aucun probleme bloquant, 1 sinon. Le script sert
donc de barriere : tant qu'il renvoie 1, on ne charge rien.

Un article "trop long" signale presque toujours un decoupage rate :
l'expression reguliere n'a pas reconnu le debut de l'article suivant, et
deux articles ont fusionne. C'est le defaut le plus sournois, parce que
la recherche remontera un bloc contenant la bonne reponse noyee dans
autre chose.

Et ces controles ne remplacent pas les yeux : l'option --echantillon
tire les articles a relire a la main contre le PDF original (B.5).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from chemins import RACINE  # noqa: F401  (ajoute backend/ au sys.path)

# La logique de controle vit dans app/services/controles.py, partagee
# avec le back-office d'administration : une seule implementation, deux
# points d'entree.
from app.services.controles import (  # noqa: F401
    AVERTISSEMENT,
    BLOQUANT,
    LONGUEUR_MAXIMALE,
    LONGUEUR_MINIMALE,
    controler,
    numero_entier,
)


def resumer(articles: list[dict]) -> None:
    """Quelques chiffres pour situer le corpus d'un coup d'oeil."""
    longueurs = sorted(len(article["contenu"]) for article in articles)
    milieu = longueurs[len(longueurs) // 2]
    pages = [article.get("page_debut", 0) for article in articles]

    print(f"  Articles          : {len(articles)}")
    print(f"  Du                : Article {articles[0]['numero']}")
    print(f"  Au                : Article {articles[-1]['numero']}")
    print(f"  Longueur mediane  : {milieu} caracteres")
    print(f"  Longueur min/max  : {longueurs[0]} / {longueurs[-1]}")
    if any(pages):
        print(f"  Pages couvertes   : {min(p for p in pages if p)} a {max(pages)}")


def echantillonner(articles: list[dict], taille: int, graine: int) -> list[dict]:
    """Tire les articles a relire a la main.

    Systematiquement le premier et le dernier - ce sont eux qui revelent
    les debuts et fins de decoupage rates - puis un tirage aleatoire
    reproductible pour le reste.
    """
    if taille >= len(articles):
        return list(articles)

    retenus = {0, len(articles) - 1}
    tirage = random.Random(graine)
    while len(retenus) < taille:
        retenus.add(tirage.randrange(len(articles)))
    return [articles[indice] for indice in sorted(retenus)]


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Controles automatiques du decoupage (B.4) et "
        "echantillon de relecture (B.5)."
    )
    analyseur.add_argument("articles", help="fichier .articles.json de 2_decouper.py")
    analyseur.add_argument(
        "--echantillon",
        type=int,
        default=0,
        help="nombre d'articles a tirer pour la relecture humaine",
    )
    analyseur.add_argument(
        "--graine",
        type=int,
        default=1,
        help="graine du tirage, pour retrouver le meme echantillon (defaut : 1)",
    )
    analyseur.add_argument(
        "--tout",
        action="store_true",
        help="lister tous les problemes au lieu des 40 premiers",
    )
    return analyseur.parse_args()


def main() -> int:
    arguments = analyser_arguments()

    chemin = Path(arguments.articles)
    if not chemin.exists():
        print(f"ERREUR : fichier introuvable -> {chemin}", file=sys.stderr)
        print("         lance d'abord ingestion/2_decouper.py", file=sys.stderr)
        return 1

    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    articles = donnees["articles"]
    texte = donnees["texte"]

    if not articles:
        print("ERREUR : aucun article dans ce fichier.", file=sys.stderr)
        return 1

    print(f"Controle de {texte['sigle']} ({texte['version']})")
    resumer(articles)
    print()

    problemes = controler(articles)
    bloquants = [message for niveau, message in problemes if niveau == BLOQUANT]
    avertissements = [
        message for niveau, message in problemes if niveau == AVERTISSEMENT
    ]

    limite = None if arguments.tout else 40

    if bloquants:
        print(f"PROBLEMES BLOQUANTS : {len(bloquants)}")
        for message in bloquants[:limite]:
            print(f"  - {message}")
        if limite and len(bloquants) > limite:
            print(f"  ... et {len(bloquants) - limite} autres (--tout pour tout voir)")
        print()

    if avertissements:
        print(f"AVERTISSEMENTS : {len(avertissements)}")
        for message in avertissements:
            print(f"  - {message}")
        print()

    if arguments.echantillon:
        retenus = echantillonner(articles, arguments.echantillon, arguments.graine)
        print(f"ECHANTILLON DE RELECTURE ({len(retenus)} articles, "
              f"graine {arguments.graine})")
        print("Compare chacun au PDF original : le numero, le chemin")
        print("hierarchique ET le contenu complet.")
        for article in retenus:
            print()
            print(f"  --- Article {article['numero']} "
                  f"(page {article.get('page_debut', '?')})")
            print(f"      {article['chemin'] or '(aucun chemin hierarchique)'}")
            print(f"      {article['contenu'][:300]}"
                  f"{'...' if len(article['contenu']) > 300 else ''}")
        print()

    if bloquants:
        print("RESULTAT : corpus NON valide. Corrige le decoupage avant de charger.")
        return 1

    print("RESULTAT : aucun probleme bloquant.")
    print("Les controles automatiques ne remplacent pas les yeux : relis un")
    print("echantillon contre le PDF avant de passer a la suite (B.5).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
