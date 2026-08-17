"""C.4 - Calibrage du seuil de refus.

Le seuil determine quand l'assistant refuse de repondre. Trop bas, il
repond n'importe quoi ; trop haut, il refuse des questions legitimes.

CE SEUIL SE CALIBRE AVEC DES DONNEES, JAMAIS AU JUGEMENT. La methode :
passer une vingtaine de questions couvertes par le corpus et une dizaine
de questions clairement hors corpus, relever le meilleur score de
pertinence obtenu a chaque fois, et placer le seuil entre les deux
nuages de points.

    python ingestion/calibrer_seuil.py evaluation/questions_calibrage.json
    python ingestion/calibrer_seuil.py ... --tableau calibrage.csv

Format du fichier d'entree :

    [
      {"question": "Nombre minimum d'associes dans une SARL ?",
       "couverte": true},
      {"question": "Duree legale du preavis de licenciement ?",
       "couverte": false}
    ]

Le tableau produit est aussi un excellent element a montrer au jury :
il prouve une demarche experimentale plutot qu'une intuition.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from chemins import RACINE  # noqa: F401  (ajoute backend/ au sys.path)

from app.services.recherche import corpus_est_vectorise, pertinence, rechercher

# Sous cet ecart entre les deux nuages, aucun seuil ne separe
# proprement : c'est le corpus ou le decoupage qu'il faut reprendre.
ECART_CONFORTABLE = 0.05


def mesurer(questions: list[dict], sigle: str | None, simuler: bool) -> list[dict]:
    """Releve le score de pertinence maximal de chaque question."""
    mesures = []
    for index, entree in enumerate(questions, 1):
        resultats = rechercher(entree["question"], sigle=sigle, simuler=simuler)
        meilleur = resultats[0][0] if resultats else None
        mesures.append(
            {
                "question": entree["question"],
                "couverte": bool(entree["couverte"]),
                "pertinence": pertinence(resultats),
                "meilleur_article": (
                    f"{meilleur['sigle']} {meilleur['numero']}" if meilleur else ""
                ),
            }
        )
        print(f"  ... {index}/{len(questions)}", end="\r", flush=True)
    # Ligne blanche : le retour chariot n'efface rien quand la sortie
    # est redirigee vers un fichier.
    print(" " * 30)
    return mesures


def afficher_nuage(titre: str, mesures: list[dict]) -> None:
    print(f"{titre} ({len(mesures)} questions)")
    for mesure in sorted(mesures, key=lambda m: m["pertinence"], reverse=True):
        question = mesure["question"][:58]
        article = mesure["meilleur_article"] or "-"
        print(f"  {mesure['pertinence']:.4f}  {question:<58}  {article}")
    print()


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Calibrage par les donnees du seuil de refus (C.4)."
    )
    analyseur.add_argument("questions", help="fichier JSON des questions de calibrage")
    analyseur.add_argument("--sigle", help="restreindre a un texte (ex. AUSCGIE)")
    analyseur.add_argument("--tableau", help="exporter le tableau des scores en CSV")
    analyseur.add_argument(
        "--simuler",
        action="store_true",
        help="vecteurs factices - le calibrage obtenu n'a aucune valeur",
    )
    return analyseur.parse_args()


def main() -> int:
    arguments = analyser_arguments()

    chemin = Path(arguments.questions)
    if not chemin.exists():
        print(f"ERREUR : fichier introuvable -> {chemin}", file=sys.stderr)
        return 1

    questions = json.loads(chemin.read_text(encoding="utf-8"))
    couvertes_attendues = [q for q in questions if q.get("couverte")]
    hors_corpus_attendues = [q for q in questions if not q.get("couverte")]

    if not couvertes_attendues or not hors_corpus_attendues:
        print(
            "ERREUR : il faut les DEUX nuages de points.\n"
            "         Le fichier doit contenir des questions couvertes "
            "(\"couverte\": true)\n"
            "         et des questions hors corpus (\"couverte\": false).",
            file=sys.stderr,
        )
        return 1

    if not corpus_est_vectorise():
        print(
            "ERREUR : aucun article vectorise en base.\n"
            "         Lance d'abord : python ingestion/4_vectoriser.py",
            file=sys.stderr,
        )
        return 1

    if arguments.simuler:
        print("ATTENTION : mode simulation, le seuil obtenu n'a aucune valeur.\n")

    print(f"Mesure de {len(questions)} questions...")
    try:
        mesures = mesurer(questions, arguments.sigle, arguments.simuler)
    except RuntimeError as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        return 1

    couvertes = [m for m in mesures if m["couverte"]]
    hors_corpus = [m for m in mesures if not m["couverte"]]

    afficher_nuage("QUESTIONS COUVERTES", couvertes)
    afficher_nuage("QUESTIONS HORS CORPUS", hors_corpus)

    plancher_couvertes = min(m["pertinence"] for m in couvertes)
    plafond_hors_corpus = max(m["pertinence"] for m in hors_corpus)

    print("SEPARATION DES DEUX NUAGES")
    print(f"  Score le plus BAS  des questions couvertes   : {plancher_couvertes:.4f}")
    print(f"  Score le plus HAUT des questions hors corpus : {plafond_hors_corpus:.4f}")
    print()

    if plancher_couvertes <= plafond_hors_corpus:
        recouvrement = plafond_hors_corpus - plancher_couvertes
        print(f"  LES DEUX NUAGES SE RECOUVRENT ({recouvrement:.4f}).")
        print("  Aucun seuil ne les separe proprement : quel que soit le")
        print("  reglage, l'assistant refusera des questions legitimes ou")
        print("  repondra hors corpus.")
        print()
        print("  Ce n'est pas un probleme de seuil. Reprends en amont :")
        print("  decoupage trop grossier, chemin hierarchique absent, ou")
        print("  prefixe manquant a la vectorisation.")
        code_retour = 1
    else:
        seuil = (plancher_couvertes + plafond_hors_corpus) / 2
        ecart = plancher_couvertes - plafond_hors_corpus
        print(f"  Ecart entre les nuages : {ecart:.4f}")
        print(f"  SEUIL_PERTINENCE={seuil:.2f}")
        if ecart < ECART_CONFORTABLE:
            print()
            print(f"  Ecart etroit (< {ECART_CONFORTABLE}) : le seuil tient sur")
            print("  peu de chose. Elargis le jeu de questions avant de t'y fier.")
        code_retour = 0

    if arguments.tableau:
        destination = Path(arguments.tableau)
        with destination.open("w", encoding="utf-8", newline="") as fichier:
            redacteur = csv.DictWriter(
                fichier,
                fieldnames=["question", "couverte", "pertinence", "meilleur_article"],
            )
            redacteur.writeheader()
            redacteur.writerows(mesures)
        print()
        print(f"Tableau des scores ecrit : {destination}")

    return code_retour


if __name__ == "__main__":
    raise SystemExit(main())
