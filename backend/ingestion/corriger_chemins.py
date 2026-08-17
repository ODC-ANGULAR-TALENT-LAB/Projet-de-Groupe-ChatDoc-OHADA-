"""Repare en place les chemins hierarchiques fabriques.

LE PROBLEME. La reconnaissance des en-tetes de niveau est insensible a
la casse — il faut bien accepter « LIVRE » comme « Livre ». Sans
frontiere apres le chiffre romain, le « l » de « la » passait pour un
romain :

    « ... a la partie la plus diligente. »
         -> niveau « Partie L », intitule « a plus diligente. »

Les articles suivants heritaient de ce niveau inexistant. Mesure au
moment de la correction : 311 articles, 29 de l'AUA et 282 de l'AUPC.

CE N'EST PAS COSMETIQUE. Le chemin est montre a l'utilisateur comme la
place de l'article dans le texte, ET il sert de prefixe a la
vectorisation (voir 4_vectoriser) : un chemin faux deplace l'article
dans l'espace semantique, donc fausse la recherche.

POURQUOI EN PLACE PLUTOT QU'UN RECHARGEMENT. Meme raison que pour les
glyphes (voir corriger_glyphes.py) : recharger recreerait les articles
avec de nouveaux identifiants, et les citations deja enregistrees —
pieces justificatives de reponses rendues — pointeraient dans le vide.

CE N'EST PAS UNE NOUVELLE VERSION DE L'ARTICLE. Le legislateur n'a rien
change ; on repare un defaut de notre propre decoupage. Le contenu
n'est pas touche, seulement sa place dans le sommaire.

L'EMBEDDING EST REMIS A NULL quand le chemin change : il a ete calcule
avec l'ancien prefixe. Le laisser en place ferait repondre la recherche
vectorielle sur un texte qui n'existe plus. 4_vectoriser le recalculera.

USAGE
    python -m ingestion.corriger_chemins <sortie/xxx.txt> [...]
    python -m ingestion.corriger_chemins --tous
    python -m ingestion.corriger_chemins --tous --appliquer
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from sqlalchemy import text

from app.db import FabriqueSession

RACINE = Path(__file__).resolve().parent
SORTIE = RACINE / "sortie"

if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

# chemins.py resout deja l'emplacement de sources/, qui vit a la racine
# du depot et non sous backend/. Le recalculer a la main ici, c'etait
# se tromper d'un niveau — et le script annoncait alors sereinement
# « tous les chemins sont a jour » sans avoir rien examine.
from chemins import DOSSIER_SOURCES  # noqa: E402


def charger_decoupeur():
    """2_decouper.py n'est pas importable : son nom commence par un chiffre."""
    specification = importlib.util.spec_from_file_location(
        "decoupeur", RACINE / "2_decouper.py"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


CORRECTION = text(
    """
    UPDATE article a
       SET chemin = :chemin,
           embedding = NULL
      FROM texte t
     WHERE t.id = a.texte_id
       AND t.sigle = :sigle
       AND a.numero = :numero
       AND a.chemin IS DISTINCT FROM :chemin
    """
)


def ecarts(session, sigle: str, chemins: dict[str, str]) -> list[tuple[str, str, str]]:
    """Articles dont le chemin en base differe du chemin recalcule."""
    lignes = session.execute(
        text(
            "SELECT a.numero, a.chemin FROM article a "
            "JOIN texte t ON t.id = a.texte_id WHERE t.sigle = :sigle"
        ),
        {"sigle": sigle},
    ).all()

    trouves = []
    for numero, actuel in lignes:
        attendu = chemins.get(numero)
        if attendu is not None and (actuel or "") != attendu:
            trouves.append((numero, actuel or "", attendu))
    return trouves


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("textes", nargs="*", help="fichiers sortie/*.txt")
    analyseur.add_argument(
        "--tous", action="store_true", help="tous les .txt du dossier sortie/"
    )
    analyseur.add_argument(
        "--appliquer",
        action="store_true",
        help="ecrit les corrections (sans ce drapeau, on ne fait que constater)",
    )
    options = analyseur.parse_args()

    fichiers = (
        sorted(f for f in SORTIE.glob("*.txt") if not f.name.endswith(".relecture.txt"))
        if options.tous
        else [Path(chemin) for chemin in options.textes]
    )
    if not fichiers:
        print("Aucun texte a traiter. Utilise --tous ou donne des chemins.")
        return 1

    decoupeur = charger_decoupeur()
    total = 0

    with FabriqueSession() as session:
        for fichier in fichiers:
            if not fichier.exists():
                print(f"  {fichier.name:34s} introuvable, ignore")
                continue

            provenance = DOSSIER_SOURCES / (fichier.stem + ".provenance.json")
            articles = decoupeur.decouper(fichier)
            if not articles:
                continue

            # Le sigle vient de la fiche de provenance ; a defaut, on
            # ne devine pas : corriger le mauvais texte serait pire que
            # ne rien corriger.
            if not provenance.exists():
                print(f"  {fichier.name:34s} pas de fiche de provenance, ignore")
                continue
            fiche = json.loads(provenance.read_text(encoding="utf-8"))
            sigle = fiche["sigle"]

            # L'EDITION DOIT ETRE CELLE QUI A ETE CHARGEE.
            #
            # Plusieurs editions d'un meme acte cohabitent dans sortie/ :
            # trois pour l'AUPC, dont une seule est complete. Elles
            # portent le meme sigle. Sans ce controle, le script les
            # corrigerait toutes a la suite, chacune ecrasant la
            # precedente — et le corpus finirait avec les chemins d'une
            # edition qui n'est pas celle de son contenu.
            #
            # L'empreinte tranche sans ambiguite : c'est celle du
            # fichier reellement ingere, enregistree a l'insertion.
            charge = session.execute(
                text("SELECT source_sha256 FROM texte WHERE sigle = :s"),
                {"s": sigle},
            ).scalar()
            if charge and fiche.get("sha256") and charge != fiche["sha256"]:
                print(
                    f"  {sigle:10s} {fichier.name[:32]:32s} "
                    "autre édition que celle chargée, ignoré"
                )
                continue

            chemins = {a["numero"]: a.get("chemin", "") for a in articles}
            trouves = ecarts(session, sigle, chemins)
            total += len(trouves)

            marque = f"{len(trouves):4d} chemin(s) a corriger" if trouves else "   à jour"
            print(f"  {sigle:10s} {fichier.name:32s} {marque}")
            for numero, actuel, attendu in trouves[:2]:
                print(f"       art.{numero}")
                print(f"         avant : {actuel[:66]!r}")
                print(f"         apres : {attendu[:66]!r}")

            if options.appliquer and trouves:
                for numero, _, attendu in trouves:
                    session.execute(
                        CORRECTION,
                        {"sigle": sigle, "numero": numero, "chemin": attendu},
                    )

        if options.appliquer:
            session.commit()
            print(f"\n{total} chemin(s) corriges. Embeddings concernes remis a NULL :")
            print("  relancer 4_vectoriser.py pour les recalculer.")
        elif total:
            print(f"\n{total} chemin(s) a corriger. Relancer avec --appliquer.")
        else:
            print("\nTous les chemins sont a jour.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
