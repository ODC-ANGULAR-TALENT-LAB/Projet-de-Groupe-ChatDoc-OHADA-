"""B.3 - Decoupage en articles (ligne de commande).

La logique de decoupage vit dans app/services/decoupage.py, partagee
avec le back-office d'administration : une seule implementation, deux
points d'entree. Ce script n'est que l'habillage ligne de commande.

A lancer depuis le dossier backend/ :

    python ingestion/2_decouper.py ingestion/sortie/auscgie_2014.txt \\
        --provenance sources/auscgie_2014.provenance.json

Produit : ingestion/sortie/auscgie_2014.articles.json

Rien n'est charge en base a ce stade : le JSON est fait pour etre relu.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chemins import DOSSIER_SORTIE, DOSSIER_SOURCES, preparer_dossiers

from app.services.decoupage import decouper_lignes

# Reexportes pour les tests et la compatibilite des appels existants.
from app.services.decoupage import (  # noqa: F401
    ESPACES_EXOTIQUES,
    RE_ARTICLE,
    RE_NIVEAUX,
    etiquette_niveau,
    normaliser,
)


def decouper(
    chemin_txt: Path, page_debut: int = 1, page_fin: int | None = None
) -> list[dict]:
    """Decoupe un fichier texte pagine."""
    with chemin_txt.open(encoding="utf-8") as fichier:
        return decouper_lignes(fichier, page_debut, page_fin)


def charger_provenance(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Decoupage d'un texte officiel en articles (B.3)."
    )
    analyseur.add_argument("texte", help="fichier .txt produit par 1_extraire.py")
    analyseur.add_argument(
        "--provenance",
        help="fiche .provenance.json du texte (defaut : deduite du nom)",
    )
    analyseur.add_argument(
        "--sortie", help="fichier JSON produit (defaut : <nom>.articles.json)"
    )
    analyseur.add_argument(
        "--page-debut",
        type=int,
        default=1,
        help="premiere page a decouper, pour sauter le sommaire (defaut : 1)",
    )
    analyseur.add_argument(
        "--page-fin", type=int, help="derniere page a decouper (defaut : la fin)"
    )
    analyseur.add_argument(
        "--apercu",
        type=int,
        default=0,
        help="afficher les N premiers articles decoupes",
    )
    return analyseur.parse_args()


def main() -> int:
    arguments = analyser_arguments()
    preparer_dossiers()

    chemin_txt = Path(arguments.texte)
    if not chemin_txt.exists():
        print(f"ERREUR : fichier introuvable -> {arguments.texte}", file=sys.stderr)
        print("         lance d'abord ingestion/1_extraire.py", file=sys.stderr)
        return 1

    if arguments.provenance:
        chemin_fiche = Path(arguments.provenance)
    else:
        chemin_fiche = DOSSIER_SOURCES / (chemin_txt.stem + ".provenance.json")
    if not chemin_fiche.exists():
        print(
            f"ERREUR : fiche de provenance introuvable -> {chemin_fiche}",
            file=sys.stderr,
        )
        return 1
    provenance = charger_provenance(chemin_fiche)

    articles = decouper(chemin_txt, arguments.page_debut, arguments.page_fin)
    if not articles:
        print(
            "ERREUR : aucun article reconnu.\n"
            "         Ouvre le fichier texte : l'en-tete des articles ne "
            "ressemble probablement pas a 'Article N'.",
            file=sys.stderr,
        )
        return 1

    destination = (
        Path(arguments.sortie)
        if arguments.sortie
        else DOSSIER_SORTIE / (chemin_txt.stem + ".articles.json")
    )
    destination.write_text(
        json.dumps(
            {"texte": provenance, "articles": articles}, indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )

    sans_chemin = sum(1 for article in articles if not article["chemin"])
    print(f"Articles ecrits : {destination}")
    print(f"  Texte            : {provenance['sigle']} ({provenance['version']})")
    print(f"  Articles         : {len(articles)}")
    print(f"  Du               : Article {articles[0]['numero']}")
    print(f"  Au               : Article {articles[-1]['numero']}")
    print(f"  Sans chemin      : {sans_chemin}")
    print()
    print("  Rien n'est charge en base : relis ce JSON avant d'aller plus loin.")
    print("  Les controles automatiques sont l'etape suivante (B.4).")

    for article in articles[: arguments.apercu]:
        extrait = article["contenu"][:200]
        print()
        print(f"  --- Article {article['numero']} (page {article['page_debut']})")
        print(f"      {article['chemin'] or '(aucun chemin hierarchique)'}")
        print(f"      {extrait}...")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
