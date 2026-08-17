"""B.7 - Generation des embeddings.

Chaque article est vectorise AVEC SON CHEMIN HIERARCHIQUE EN PREFIXE.
Un article isole est souvent incomprehensible ; "AUSCGIE > Livre I >
Titre II - Des assemblees generales > Article 337 : ..." porte beaucoup
plus de sens que "Article 337 : ...". Ce detail ameliore nettement la
pertinence de la recherche.

    python ingestion/4_vectoriser.py
    python ingestion/4_vectoriser.py --sigle AUSCGIE --creer-index

Traitement par lots pour limiter le nombre d'appels. Le script est
reprenable : il ne traite que les articles dont l'embedding est encore
nul, donc une interruption ne fait perdre que le lot en cours.

L'index HNSW se cree APRES l'insertion de tous les vecteurs, jamais
avant : la construction sur une table deja remplie est bien plus rapide,
et l'index se maintient ensuite tout seul.
"""

from __future__ import annotations

import argparse
import sys

from chemins import RACINE  # noqa: F401  (ajoute backend/ au sys.path)

from app.db import moteur

# LA LOGIQUE VIT DANS app/services/vectorisation.py, partagee avec le
# back-office du juriste. Ce script n'en est que l'habillage en ligne de
# commande : deux implementations produiraient deux representations du
# meme article selon la porte empruntee.
from app.services.vectorisation import (  # noqa: F401  (reexporte pour les tests)
    TAILLE_LOT,
    VectorisationImpossible,
    articles_a_traiter,
    creer_index,
    enregistrer_vecteurs,
    texte_a_vectoriser,
    vectoriser,
)


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Generation des embeddings des articles (B.7)."
    )
    analyseur.add_argument("--sigle", help="ne traiter qu'un texte (ex. AUSCGIE)")
    analyseur.add_argument(
        "--limite", type=int, help="ne traiter que les N premiers articles"
    )
    analyseur.add_argument(
        "--simuler",
        action="store_true",
        help="vecteurs factices, sans appel reseau - test de tuyauterie SEULEMENT",
    )
    analyseur.add_argument(
        "--creer-index",
        action="store_true",
        help="construire l'index HNSW une fois tous les vecteurs ecrits",
    )
    return analyseur.parse_args()


def main() -> int:
    arguments = analyser_arguments()

    if arguments.simuler:
        print("=" * 68)
        print("  MODE SIMULATION : les vecteurs produits sont ALEATOIRES.")
        print("  Ils servent a verifier la tuyauterie, rien d'autre.")
        print("  Toute recherche fondee dessus est denuee de sens.")
        print("  Revectorise avec le vrai fournisseur avant tout usage.")
        print("=" * 68)
        print()

    with moteur.begin() as cx:
        restants = len(articles_a_traiter(cx, arguments.sigle, arguments.limite))

    if not restants:
        print("Aucun article a vectoriser : tout est deja fait.")
        if arguments.creer_index:
            with moteur.begin() as cx:
                creer_index(cx)
        return 0

    print(f"{restants} article(s) a vectoriser, par lots de {TAILLE_LOT}.")

    try:
        traites = vectoriser(
            moteur,
            sigle=arguments.sigle,
            limite=arguments.limite,
            simuler=arguments.simuler,
            progression=lambda faits, total: print(
                f"  ... {faits}/{total} articles", flush=True
            ),
        )
    except VectorisationImpossible as erreur:
        print(f"\nERREUR : {erreur}", file=sys.stderr)
        return 1

    print()
    print(f"Vectorisation terminee : {traites} article(s).")

    if arguments.creer_index:
        with moteur.begin() as cx:
            creer_index(cx)
    else:
        print()
        print("L'index vectoriel n'est pas encore construit. Une fois TOUS les")
        print("vecteurs en place : python ingestion/4_vectoriser.py --creer-index")

    if arguments.simuler:
        print()
        print("RAPPEL : ces vecteurs sont factices. Le corpus n'est pas exploitable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
