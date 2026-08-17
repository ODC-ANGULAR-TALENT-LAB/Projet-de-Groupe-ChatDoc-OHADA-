"""D.3 - Le script d'evaluation.

Rejoue le jeu de 50 questions contre l'API et publie les taux. C'est le
seul test qui mesure la promesse du produit : rejoue-le A CHAQUE
modification du pipeline - seuil, prompt, decoupage, modele.

    python evaluation/lancer_eval.py --email eval@exemple.test --mot-de-passe ...

Le jeu de questions doit etre FIGE avant toute optimisation. Ecrit
apres, il serait inconsciemment redige pour reussir, et la mesure ne
vaudrait rien.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

RACINE = Path(__file__).resolve().parent
FICHIER_QUESTIONS = RACINE / "questions.json"
MODELE = RACINE / "questions.modele.json"

# Composition imposee par le guide (D.1).
COMPOSITION_ATTENDUE = {
    "factuelle": 25,
    "multi_articles": 10,
    "formulation_indirecte": 5,
    "piege_hors_corpus": 5,
    "piege_actualite": 5,
}

# Cible du cahier des charges : une reponse en moins de 10 secondes.
CIBLE_SECONDES = 10.0


def reference(sigle: str, numero: str) -> str:
    """Reference complete et comparable d'un article : « AUS 13 ».

    Le sigle est indispensable : un numero seul ne designe rien dans un
    corpus de neuf actes qui numerotent tous a partir de 1.
    """
    return f"{str(sigle).strip().upper()} {str(numero).strip()}"


def reference_attendue(brut: str) -> str:
    """Normalise une entree d'`articles_attendus`.

    Attend la forme « SIGLE numero ». Un numero seul est refuse : il
    serait ambigu, et le laisser passer reviendrait a mesurer autre chose
    que ce qu'on croit mesurer.
    """
    morceaux = str(brut).strip().split(None, 1)
    if len(morceaux) != 2:
        raise SystemExit(
            f"Article attendu ambigu : {brut!r}.\n"
            "Ecris la reference complete, sigle compris — par exemple "
            '"AUS 13". Un numero seul existe dans plusieurs actes.'
        )
    return reference(morceaux[0], morceaux[1])


def charger_questions(chemin: Path) -> list[dict]:
    if not chemin.exists():
        raise SystemExit(
            f"ERREUR : {chemin.name} introuvable.\n"
            f"         Copie {MODELE.name} en {chemin.name} et remplis-le avec\n"
            "         de vraies questions dont tu as verifie la reponse dans le\n"
            "         texte officiel."
        )
    questions = [q for q in json.loads(chemin.read_text(encoding="utf-8")) if "id" in q]
    if not questions:
        raise SystemExit(f"ERREUR : aucune question exploitable dans {chemin.name}.")
    return questions


def controler_composition(questions: list[dict]) -> list[str]:
    """Compare la composition reelle a celle qu'impose le guide."""
    ecarts = []
    reels = {}
    for question in questions:
        reels[question["type"]] = reels.get(question["type"], 0) + 1

    for type_attendu, attendu in COMPOSITION_ATTENDUE.items():
        reel = reels.get(type_attendu, 0)
        if reel != attendu:
            ecarts.append(f"{type_attendu} : {reel} au lieu de {attendu}")

    inconnus = set(reels) - set(COMPOSITION_ATTENDUE)
    if inconnus:
        ecarts.append(f"types inconnus : {sorted(inconnus)}")
    return ecarts


def obtenir_jeton(base: str, email: str, mot_de_passe: str) -> str:
    reponse = httpx.post(
        f"{base}/auth/connexion",
        json={"email": email, "mot_de_passe": mot_de_passe},
        timeout=30,
    )
    if reponse.status_code != 200:
        raise SystemExit(
            f"ERREUR : connexion refusee ({reponse.status_code}).\n"
            "         Cree d'abord le compte via POST /auth/inscription."
        )
    return reponse.json()["jeton_acces"]


def interroger(base: str, jeton: str, question: str) -> tuple[dict, float]:
    depart = time.perf_counter()
    reponse = httpx.post(
        f"{base}/chat/question",
        json={"question": question},
        headers={"Authorization": f"Bearer {jeton}"},
        timeout=120,
    )
    duree = time.perf_counter() - depart

    if reponse.status_code == 402:
        raise SystemExit(
            "ERREUR : quota epuise en cours d'evaluation.\n"
            "         Le compte d'evaluation a besoin d'un quota superieur au\n"
            "         nombre de questions. En local :\n"
            "         docker compose exec db psql -U chatdocs -d chatdocs -c \\\n"
            '           "UPDATE utilisateur SET quota_restant = 500;"'
        )
    reponse.raise_for_status()
    return reponse.json(), duree


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(description="Jeu d'evaluation (D.3).")
    analyseur.add_argument("--base", default="http://localhost:8000")
    analyseur.add_argument("--email", required=True)
    analyseur.add_argument("--mot-de-passe", required=True)
    analyseur.add_argument("--questions", default=str(FICHIER_QUESTIONS))
    analyseur.add_argument("--rapport", help="ecrire le rapport JSON dans ce fichier")
    analyseur.add_argument(
        "--ignorer-composition",
        action="store_true",
        help="lancer meme si la composition s'ecarte des 50 questions attendues",
    )
    return analyseur.parse_args()


def main() -> int:
    arguments = analyser_arguments()
    questions = charger_questions(Path(arguments.questions))

    ecarts = controler_composition(questions)
    if ecarts:
        print(f"Composition du jeu : {len(questions)} questions")
        for ecart in ecarts:
            print(f"  - {ecart}")
        if not arguments.ignorer_composition:
            print()
            print("Le guide impose 25/10/5/5/5. Relance avec --ignorer-composition")
            print("pour mesurer quand meme un jeu partiel.", file=sys.stderr)
            return 1
        print("  (--ignorer-composition : on mesure quand meme)\n")

    jeton = obtenir_jeton(arguments.base, arguments.email, arguments.mot_de_passe)

    ok_citations = ok_refus = total_refus = 0
    durees: list[float] = []
    echecs: list[dict] = []

    for question in questions:
        resultat, duree = interroger(arguments.base, jeton, question["question"])
        durees.append(duree)

        a_refuse = (
            resultat.get("confiance") == "insuffisante" or resultat.get("refus") is True
        )

        if question["doit_refuser"]:
            total_refus += 1
            if a_refuse:
                ok_refus += 1
            else:
                echecs.append(
                    {
                        "id": question["id"],
                        "motif": "aurait du refuser",
                        "reponse": resultat["reponse"][:120],
                    }
                )
                print(f"[{question['id']}] AURAIT DU REFUSER -> "
                      f"{resultat['reponse'][:90]}")
        else:
            # LE SIGLE FAIT PARTIE DE LA REFERENCE. Un numero nu est
            # ambigu : l'article 13 existe dans les NEUF actes du corpus.
            # Comparer sans le sigle compterait juste une reponse citant
            # l'article 13 de l'AUDCG (livres de commerce) a une question
            # portant sur l'article 13 de l'AUS (cautionnement) — un faux
            # positif qui flatte le score, soit exactement le sens dans
            # lequel une mesure ne doit jamais se tromper.
            cites = {reference(c["sigle"], c["numero"]) for c in resultat.get("citations", [])}
            attendus = {reference_attendue(n) for n in question["articles_attendus"]}
            if attendus & cites:
                ok_citations += 1
            else:
                echecs.append(
                    {
                        "id": question["id"],
                        "motif": "citation manquante",
                        "attendus": sorted(attendus),
                        "cites": sorted(cites),
                    }
                )
                print(f"[{question['id']}] attendu {sorted(attendus)}, "
                      f"cite {sorted(cites)}")

    total_repondre = len(questions) - total_refus
    print()
    print("=" * 60)
    if total_repondre:
        taux = 100 * ok_citations / total_repondre
        print(f"Citations correctes : {ok_citations}/{total_repondre} ({taux:.0f} %)")
    if total_refus:
        print(f"Refus corrects      : {ok_refus}/{total_refus}")
    print(f"Temps median        : {statistics.median(durees):.1f} s")
    print(f"Temps le plus long  : {max(durees):.1f} s "
          f"(cible : moins de {CIBLE_SECONDES:.0f} s)")
    hors_cible = sum(1 for duree in durees if duree > CIBLE_SECONDES)
    if hors_cible:
        print(f"Hors cible          : {hors_cible} question(s) au-dela de "
              f"{CIBLE_SECONDES:.0f} s")
    print("=" * 60)

    if arguments.rapport:
        Path(arguments.rapport).write_text(
            json.dumps(
                {
                    "questions": len(questions),
                    "citations_correctes": ok_citations,
                    "questions_a_repondre": total_repondre,
                    "refus_corrects": ok_refus,
                    "refus_attendus": total_refus,
                    "temps_median_s": round(statistics.median(durees), 2),
                    "temps_max_s": round(max(durees), 2),
                    "echecs": echecs,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nRapport ecrit : {arguments.rapport}")

    return 0 if not echecs else 1


if __name__ == "__main__":
    raise SystemExit(main())
