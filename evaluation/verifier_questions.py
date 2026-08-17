"""Verifie que le jeu d'evaluation repose sur des articles REELS.

POURQUOI CE SCRIPT EXISTE. Le modele de questions le dit sans detour :
« ne devine jamais un numero d'article : une question fondee sur un
article inexistant fausse la mesure dans le sens le plus dangereux,
celui qui te rassure ». Une question dont l'article attendu n'existe pas
ne pourra JAMAIS etre satisfaite : elle fait chuter le taux de citations
correctes sans que le pipeline y soit pour rien — ou, pire, elle passe
inapercue et on croit mesurer autre chose que ce qu'on mesure.

Ce script relit chaque `articles_attendus` en base et rend un code de
retour non nul si l'un d'eux est introuvable. A jouer AVANT de figer le
jeu, et rejouer apres toute mise a jour du corpus : une revision qui
abroge un article rend caduque la question qui s'appuyait dessus.

    python evaluation/verifier_questions.py evaluation/questions.json

Il ne verifie PAS que la reponse attendue est juridiquement exacte —
cela releve de la relecture par un professionnel du domaine (§15). Il
verifie que la question est mesurable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(RACINE))

from sqlalchemy import text  # noqa: E402

from app.db import moteur  # noqa: E402

TYPES_SANS_ARTICLE = {"piege_hors_corpus", "piege_actualite"}


def charger(chemin: Path) -> list[dict]:
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    # La premiere entree est l'en-tete de composition, pas une question.
    return [entree for entree in donnees if "id" in entree]


def articles_en_vigueur(cx) -> dict[str, str]:
    """« SIGLE numero » -> debut du contenu, pour les articles en vigueur.

    LA CLE PORTE LE SIGLE. Un numero seul ne designe rien : l'article 13
    existe dans les neuf actes du corpus, et « article 13 » renvoie au
    cautionnement dans l'AUS comme aux livres de commerce dans l'AUDCG.
    """
    index: dict[str, str] = {}
    for ligne in cx.execute(
        text(
            "SELECT t.sigle, a.numero, left(a.contenu, 160) AS extrait "
            "FROM article a JOIN texte t ON t.id = a.texte_id "
            "WHERE a.date_abrogation IS NULL"
        )
    ):
        index[f"{ligne.sigle.upper()} {ligne.numero}"] = " ".join(ligne.extrait.split())
    return index


def normaliser(brut: str) -> str | None:
    """« AUS 13 » -> « AUS 13 ». Rend None si le sigle manque."""
    morceaux = str(brut).strip().split(None, 1)
    if len(morceaux) != 2:
        return None
    return f"{morceaux[0].upper()} {morceaux[1].strip()}"


def verifier(questions: list[dict], index: dict[str, list[str]]) -> list[str]:
    problemes: list[str] = []

    for question in questions:
        attendus = [str(n) for n in question.get("articles_attendus", [])]
        type_question = question.get("type", "")

        if type_question in TYPES_SANS_ARTICLE:
            # Un piege DOIT etre sans article attendu : lui en donner un
            # reviendrait a demander un refus tout en fournissant de quoi
            # ne pas refuser.
            if attendus:
                problemes.append(
                    f"[{question['id']}] type {type_question} mais "
                    f"{len(attendus)} article(s) attendu(s) : un piege se "
                    "mesure sur le refus, pas sur la citation."
                )
            if not question.get("doit_refuser"):
                problemes.append(
                    f"[{question['id']}] type {type_question} mais "
                    "doit_refuser est faux."
                )
            continue

        if not attendus:
            problemes.append(
                f"[{question['id']}] aucun article attendu pour une question "
                "a laquelle l'assistant doit repondre."
            )
            continue

        for brut in attendus:
            reference = normaliser(brut)
            if reference is None:
                problemes.append(
                    f"[{question['id']}] reference ambigue : {brut!r}. Ecris "
                    'le sigle — par exemple "AUS 13". Un numero seul existe '
                    "dans plusieurs actes, et la mesure compterait juste une "
                    "citation portant sur un tout autre texte."
                )
                continue
            if reference not in index:
                problemes.append(
                    f"[{question['id']}] {reference} INTROUVABLE en base "
                    "— la question ne pourra jamais etre satisfaite."
                )

    return problemes


def composition(questions: list[dict]) -> dict[str, int]:
    compte: dict[str, int] = {}
    for question in questions:
        compte[question.get("type", "?")] = compte.get(question.get("type", "?"), 0) + 1
    return compte


def main() -> int:
    analyseur = argparse.ArgumentParser(
        description="Verifie que le jeu d'evaluation repose sur des articles reels."
    )
    analyseur.add_argument(
        "questions",
        nargs="?",
        default=str(Path(__file__).parent / "questions.json"),
        help="fichier questions.json",
    )
    arguments = analyseur.parse_args()

    chemin = Path(arguments.questions)
    if not chemin.exists():
        print(f"ERREUR : fichier introuvable -> {chemin}", file=sys.stderr)
        return 1

    questions = charger(chemin)
    print(f"{len(questions)} question(s) lues dans {chemin.name}")
    for type_question, nombre in sorted(composition(questions).items()):
        print(f"  {type_question:<24} {nombre}")
    print()

    with moteur.begin() as cx:
        index = articles_en_vigueur(cx)
    print(f"{len(index)} numero(s) d'article distincts en vigueur dans le corpus.")
    print()

    problemes = verifier(questions, index)
    if problemes:
        print(f"PROBLEMES : {len(problemes)}")
        for probleme in problemes:
            print(f"  - {probleme}")
        print()
        print("Le jeu N'EST PAS mesurable en l'etat.")
        return 1

    # LE DEBUT DE CHAQUE ARTICLE EST IMPRIME. C'est ce qui permet la
    # relecture humaine : verifier qu'une question sur le cautionnement
    # pointe bien vers le cautionnement, et non vers l'article portant le
    # meme numero dans un autre acte.
    print("Articles attendus, avec le debut de leur contenu reel :")
    for question in questions:
        attendus = [normaliser(n) for n in question.get("articles_attendus", [])]
        attendus = [a for a in attendus if a]
        if not attendus:
            continue
        print(f"  [{question['id']:>2}] {question['question'][:70]}")
        for reference in attendus:
            print(f"       {reference:<14} {index[reference][:96]}")

    print()
    print("Toutes les references attendues existent en base, sigle compris.")
    print("Reste la relecture par un professionnel : ce script ne verifie pas")
    print("que la reponse attendue est juridiquement exacte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
