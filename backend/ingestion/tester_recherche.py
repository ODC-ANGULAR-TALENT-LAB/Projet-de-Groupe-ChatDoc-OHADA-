"""C.3 - Test manuel de la recherche, en ligne de commande.

Sans interface, sans LLM. On verifie une seule chose : est-ce que les
bons articles remontent ?

    python ingestion/tester_recherche.py "delai de convocation AG SARL"
    python ingestion/tester_recherche.py "..." --sigle AUSCGIE --detail

Lance-le sur une trentaine de questions dont tu connais la reponse. Pour
chacune, l'article attendu doit apparaitre DANS LES TROIS PREMIERS
RESULTATS. Si ce n'est pas le cas, le probleme est en amont : decoupage
trop grossier, chemin hierarchique absent, ou prefixe manquant a la
vectorisation. Ne cherche pas a corriger la recherche elle-meme.
"""

from __future__ import annotations

import argparse
import sys

from chemins import RACINE  # noqa: F401  (ajoute backend/ au sys.path)

from app.config import parametres
from app.services.recherche import corpus_est_vectorise, pertinence, rechercher

LARGEUR_EXTRAIT = 220


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Test manuel de la recherche hybride (C.3)."
    )
    analyseur.add_argument("question", nargs="+", help="la question a poser")
    analyseur.add_argument("--sigle", help="restreindre a un texte (ex. AUSCGIE)")
    analyseur.add_argument(
        "-n", type=int, help=f"nombre de resultats (defaut : {parametres.nb_articles_contexte})"
    )
    analyseur.add_argument(
        "--detail",
        action="store_true",
        help="afficher le detail des scores vectoriel et lexical",
    )
    analyseur.add_argument(
        "--simuler",
        action="store_true",
        help="vecteurs factices - n'a de sens que sur un corpus lui-meme simule",
    )
    return analyseur.parse_args()


def main() -> int:
    arguments = analyser_arguments()
    question = " ".join(arguments.question)

    if not corpus_est_vectorise():
        print(
            "ERREUR : aucun article vectorise en base.\n"
            "         La moitie vectorielle de la recherche ne remonterait "
            "rien, et le\n"
            "         systeme se degraderait silencieusement en simple "
            "recherche plein texte.\n"
            "         Lance d'abord : python ingestion/4_vectoriser.py",
            file=sys.stderr,
        )
        return 1

    try:
        resultats = rechercher(
            question, n=arguments.n, sigle=arguments.sigle, simuler=arguments.simuler
        )
    except RuntimeError as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        return 1

    print(f'Question : "{question}"')
    if not resultats:
        print("Aucun resultat.")
        return 0

    meilleure = pertinence(resultats)
    seuil = parametres.seuil_pertinence
    verdict = "REPONDRAIT" if meilleure >= seuil else "REFUSERAIT"
    print(f"Pertinence maximale : {meilleure:.4f} "
          f"(seuil {seuil}) -> l'assistant {verdict}")
    print()

    for rang, (article, score_rrf) in enumerate(resultats, 1):
        marque = " <- attendu dans le top 3" if rang <= 3 else ""
        print(f"[{rang}] rrf={score_rrf:.4f}  "
              f"{article['sigle']} - Article {article['numero']}{marque}")
        print(f"    {article['chemin']}")
        if arguments.detail:
            print(f"    vectoriel={article['score_vectoriel']:.4f}  "
                  f"lexical={article['score_lexical']:.4f}")
        extrait = article["contenu"][:LARGEUR_EXTRAIT]
        suite = "..." if len(article["contenu"]) > LARGEUR_EXTRAIT else ""
        print(f"    {extrait}{suite}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
