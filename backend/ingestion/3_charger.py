"""B.6 - Chargement en base.

Insere un texte et ses articles dans PostgreSQL, en une seule
transaction : soit tout passe, soit rien.

    python ingestion/3_charger.py ingestion/sortie/auscgie_2014.articles.json

Les controles de B.4 sont rejoues ici, en barriere. Un corpus qui ne
passe pas les controles n'entre pas en base : c'est le seul moment ou
l'erreur est encore facile a corriger.

REGLE ABSOLUE : aucun UPDATE sur le contenu d'un article. Une
modification legale clot l'ancienne ligne (date_abrogation) et en insere
une nouvelle. Ce script n'ecrit donc jamais par-dessus l'existant ; il
refuse une version deja chargee.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

from chemins import preparer_dossiers  # noqa: F401  (ajoute backend/ au sys.path)
from controler import BLOQUANT, controler

from app.db import moteur

# Les insertions partent par paquets : un acte uniforme depasse le
# millier d'articles, et un aller-retour par ligne est inutilement lent.
TAILLE_LOT = 200


def version_existante(cx, sigle: str, version: str) -> int | None:
    """Identifiant du texte deja charge pour ce couple sigle/version."""
    return cx.execute(
        text("SELECT id FROM texte WHERE sigle = :s AND version = :v"),
        {"s": sigle, "v": version},
    ).scalar()


def compter_citations(cx, texte_id: int) -> int:
    """Nombre de citations pointant vers les articles de ce texte.

    Tant que ce compte est nul, la suppression d'une ingestion ratee est
    sans consequence. Des qu'il ne l'est plus, des reponses rendues a
    des utilisateurs s'appuient dessus : on ne touche plus a rien.
    """
    return cx.execute(
        text(
            "SELECT count(*) FROM citation c "
            "JOIN article a ON a.id = c.article_id "
            "WHERE a.texte_id = :t"
        ),
        {"t": texte_id},
    ).scalar()


def supprimer_version(cx, texte_id: int) -> int:
    """Efface une ingestion defectueuse. Reserve au developpement.

    L'ORDRE SUIT LES CLES ETRANGERES : article, puis depot, puis texte.
    Le depot est arrive avec le back-office d'administration et personne
    n'a repasse ici : la suppression echouait alors sur une violation de
    contrainte, apres avoir deja efface les articles. La transaction du
    programme appelant annule tout, mais le message d'erreur, lui,
    n'apprenait rien.
    """
    supprimes = cx.execute(
        text("DELETE FROM article WHERE texte_id = :t"), {"t": texte_id}
    ).rowcount
    # Le depot garde la trace du fichier televerse ; on le detache du
    # texte plutot que de le supprimer, pour ne pas perdre l'historique
    # des validations de l'administrateur.
    cx.execute(
        text("UPDATE depot SET texte_id = NULL WHERE texte_id = :t"), {"t": texte_id}
    )
    cx.execute(text("DELETE FROM texte WHERE id = :t"), {"t": texte_id})
    return supprimes


def inserer_texte(cx, fiche: dict) -> int:
    """Cree la ligne texte et renvoie son identifiant."""
    return cx.execute(
        text(
            """
            INSERT INTO texte (sigle, titre, type, version, date_consolidation,
                               source_url, source_sha256, valide_par)
            VALUES (:sigle, :titre, :type, :version, :date_conso,
                    :url, :sha, :valide_par)
            RETURNING id
            """
        ),
        {
            "sigle": fiche["sigle"],
            "titre": fiche["titre"],
            "type": fiche["type"],
            "version": fiche["version"],
            "date_conso": fiche["date_consolidation"],
            "url": fiche["url_source"],
            "sha": fiche["sha256"],
            "valide_par": fiche["valide_par"],
        },
    ).scalar()


def inserer_articles(cx, texte_id: int, articles: list[dict], date_conso: str) -> None:
    """Insere les articles par lots, avec leur index plein texte.

    recherche_fts est calcule ici, en base : c'est PostgreSQL qui
    connait la configuration 'french', pas Python.
    """
    requete = text(
        """
        INSERT INTO article (texte_id, numero, chemin, contenu,
                             date_entree_vigueur, recherche_fts)
        VALUES (:texte_id, :numero, :chemin, :contenu,
                :date_vigueur, to_tsvector('french', :contenu))
        """
    )
    for debut in range(0, len(articles), TAILLE_LOT):
        lot = articles[debut : debut + TAILLE_LOT]
        cx.execute(
            requete,
            [
                {
                    "texte_id": texte_id,
                    "numero": article["numero"],
                    "chemin": article["chemin"],
                    "contenu": article["contenu"],
                    "date_vigueur": date_conso,
                }
                for article in lot
            ],
        )
        print(f"  ... {min(debut + TAILLE_LOT, len(articles))}/{len(articles)} articles",
              flush=True)


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Chargement d'un texte decoupe en base (B.6)."
    )
    analyseur.add_argument("articles", help="fichier .articles.json de 2_decouper.py")
    analyseur.add_argument(
        "--remplacer",
        action="store_true",
        help="supprimer d'abord la version deja chargee (ingestion ratee)",
    )
    analyseur.add_argument(
        "--ignorer-controles",
        action="store_true",
        help="charger malgre des problemes bloquants - a n'utiliser que si "
        "tu sais precisement pourquoi",
    )
    return analyseur.parse_args()


def main() -> int:
    arguments = analyser_arguments()

    chemin = Path(arguments.articles)
    if not chemin.exists():
        print(f"ERREUR : fichier introuvable -> {chemin}", file=sys.stderr)
        return 1

    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    fiche, articles = donnees["texte"], donnees["articles"]
    if not articles:
        print("ERREUR : aucun article a charger.", file=sys.stderr)
        return 1

    # 1) barriere : les controles de B.4
    bloquants = [
        message for niveau, message in controler(articles) if niveau == BLOQUANT
    ]
    if bloquants:
        # Tout part sur la meme sortie : sinon les lignes s'entrelacent
        # et le message devient illisible.
        flux = sys.stdout if arguments.ignorer_controles else sys.stderr
        print(f"CONTROLES : {len(bloquants)} probleme(s) bloquant(s)", file=flux)
        for message in bloquants[:10]:
            print(f"  - {message}", file=flux)
        if len(bloquants) > 10:
            print(f"  ... et {len(bloquants) - 10} autres", file=flux)
        if not arguments.ignorer_controles:
            print(file=flux)
            print("Rien n'a ete charge. Corrige le decoupage, ou relance", file=flux)
            print("avec --ignorer-controles si tu assumes ces defauts.", file=flux)
            return 1
        print("  (--ignorer-controles : on continue quand meme)")
        print()

    # 2) chargement, tout ou rien
    try:
        with moteur.begin() as cx:
            ancien = version_existante(cx, fiche["sigle"], fiche["version"])
            if ancien is not None:
                citations = compter_citations(cx, ancien)
                if not arguments.remplacer:
                    print(
                        f"ERREUR : {fiche['sigle']} ({fiche['version']}) est deja "
                        f"charge (texte id={ancien}).\n"
                        "         Une version chargee ne se remplace pas : une "
                        "modification legale\n"
                        "         clot l'ancienne et en insere une nouvelle.\n"
                        "         Pour effacer une ingestion RATEE : --remplacer",
                        file=sys.stderr,
                    )
                    return 1
                if citations:
                    print(
                        f"ERREUR : {citations} citation(s) pointent vers les "
                        "articles de cette version.\n"
                        "         Des reponses rendues s'appuient dessus : "
                        "suppression refusee.",
                        file=sys.stderr,
                    )
                    return 1
                supprimes = supprimer_version(cx, ancien)
                print(f"Version precedente supprimee ({supprimes} articles).")

            texte_id = inserer_texte(cx, fiche)
            print(f"Texte insere : id={texte_id}")
            inserer_articles(cx, texte_id, articles, fiche["date_consolidation"])

            total = cx.execute(
                text("SELECT count(*) FROM article WHERE texte_id = :t"),
                {"t": texte_id},
            ).scalar()
    except Exception as erreur:  # noqa: BLE001 - diagnostic utile a l'utilisateur
        print(f"ERREUR : le chargement a echoue, rien n'a ete ecrit.\n{erreur}",
              file=sys.stderr)
        return 1

    print()
    print(f"Charge : {fiche['sigle']} ({fiche['version']}) - {total} articles")
    print(f"  Provenance : {fiche['url_source']}")
    print(f"  SHA-256    : {fiche['sha256'][:16]}...")
    print(f"  Valide par : {fiche['valide_par']}")
    print()
    print("Les embeddings ne sont pas encore calcules :")
    print("  python ingestion/4_vectoriser.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
