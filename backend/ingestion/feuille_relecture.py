"""B.5 - Feuille de relecture humaine, a comparer au PDF original.

`controler.py --echantillon` tire deja les articles a relire, mais il
tronque leur contenu a 300 caracteres pour rester lisible au terminal.
Or la FIN d'un article est precisement l'endroit ou se voit le defaut le
plus grave du decoupage : quand l'en-tete de l'article suivant n'a pas
ete reconnu, son texte s'ajoute a la queue du precedent. C'est ce qui
s'est produit sur l'AUPC, dont cinq articles en absorbaient un autre.
Une relecture sur les 300 premiers caracteres ne l'aurait jamais vu.

Ce script produit donc la meme selection, contenu entier, dans un
fichier qu'on lit a cote du PDF :

    python ingestion/feuille_relecture.py ingestion/sortie/aus_2010.articles.json

Produit : ingestion/sortie/aus_2010.relecture.txt

Le tirage est celui de controler.py, importe et non recopie : a graine
egale, les deux outils designent les memes articles.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chemins import RACINE  # noqa: F401  (ajoute backend/ au sys.path)
from controler import echantillonner


def rediger(donnees: dict, taille: int, graine: int) -> str:
    articles = donnees["articles"]
    texte = donnees["texte"]
    retenus = echantillonner(articles, taille, graine)

    lignes = [
        f"FEUILLE DE RELECTURE - {texte['sigle']} ({texte['version']})",
        f"PDF de reference : {texte['fichier']}",
        f"Echantillon : {len(retenus)} articles sur {len(articles)}, graine {graine}",
        "",
        "Pour CHAQUE article, verifie contre le PDF, dans cet ordre :",
        "  1. le numero et la page",
        "  2. le chemin hierarchique (livre / titre / chapitre / section)",
        "  3. le DEBUT du contenu : rien du texte de l'article precedent",
        "  4. la FIN du contenu : rien du texte de l'article suivant",
        "",
        "Le point 4 est le plus important : c'est par la que passent les",
        "articles fusionnes, et ils ne se voient pas autrement.",
        "",
    ]

    for article in retenus:
        lignes += [
            "=" * 70,
            f"Article {article['numero']}  (page {article.get('page_debut', '?')})",
            f"  chemin : {article['chemin'] or '(aucun chemin hierarchique)'}",
            f"  taille : {len(article['contenu'])} caracteres",
            "",
            article["contenu"],
            "",
            "  [ ] numero et page exacts",
            "  [ ] chemin hierarchique exact",
            "  [ ] debut du contenu exact",
            "  [ ] fin du contenu exacte",
            "",
        ]

    return "\n".join(lignes) + "\n"


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Feuille de relecture humaine d'un corpus decoupe (B.5)."
    )
    analyseur.add_argument("articles", help="fichier .articles.json de 2_decouper.py")
    analyseur.add_argument(
        "--echantillon", type=int, default=20, help="nombre d'articles (defaut : 20)"
    )
    analyseur.add_argument(
        "--graine",
        type=int,
        default=1,
        help="graine du tirage, la meme que controler.py (defaut : 1)",
    )
    return analyseur.parse_args()


def main() -> int:
    arguments = analyser_arguments()

    chemin = Path(arguments.articles)
    if not chemin.exists():
        print(f"ERREUR : fichier introuvable -> {chemin}", file=sys.stderr)
        return 1

    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    if not donnees.get("articles"):
        print("ERREUR : aucun article dans ce fichier.", file=sys.stderr)
        return 1

    feuille = rediger(donnees, arguments.echantillon, arguments.graine)
    destination = chemin.with_suffix("").with_suffix(".relecture.txt")
    destination.write_text(feuille, encoding="utf-8")

    print(f"Feuille ecrite : {destination}")
    print(f"  Articles a relire : {min(arguments.echantillon, len(donnees['articles']))}")
    print("  Relis-la contre le PDF avant de charger quoi que ce soit (B.6).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
