"""Repare en place les glyphes de police symbolique restes en base.

LE PROBLEME. Certains PDF officiels composent leurs puces de liste avec
une police symbolique : le caractere stocke n'est pas « • » mais un
glyphe de la zone privee Unicode (U+F0B7), qui n'a de sens que pour
cette police. Charge tel quel, il part dans le contenu de l'article,
donc dans l'extrait presente a l'utilisateur COMME TEXTE OFFICIEL.

L'ingestion sait desormais les traduire (decoupage.normaliser), mais les
articles charges avant cette correction gardent les glyphes.

POURQUOI UNE CORRECTION EN PLACE PLUTOT QU'UN RECHARGEMENT. Recharger
l'acte recreerait les articles avec de nouveaux identifiants, et les
citations deja enregistrees pointeraient dans le vide — or ces citations
sont la piece justificative d'une reponse rendue. La correction en place
conserve les identifiants : les citations restent verifiables.

CE QUI N'EST PAS TOUCHE : citation.extrait. C'est un instantane de ce
qui a ete MONTRE a l'utilisateur, pas une copie du corpus. Le reecrire
reviendrait a falsifier la trace. Le glyphe y est neutralise au rendu
(voir export_pdf._echapper), ce qui est le bon endroit : on corrige
l'affichage sans retoucher l'archive.

CE N'EST PAS UNE NOUVELLE VERSION DE L'ARTICLE. La regle « un article
n'est jamais ecrase » protege l'historique JURIDIQUE : une revision cree
une version, elle ne remplace pas l'ancienne. Ici le legislateur n'a
rien change — on repare un defaut de notre propre extraction. Ouvrir une
version pour cela reviendrait a archiver un bogue comme s'il s'agissait
d'un etat du droit.

USAGE
    python -m ingestion.corriger_glyphes              # constate
    python -m ingestion.corriger_glyphes --appliquer  # corrige
"""

from __future__ import annotations

import argparse
import re

from sqlalchemy import text

from app.db import FabriqueSession
from app.services.decoupage import (
    DEBUT_ZONE_PRIVEE,
    FIN_ZONE_PRIVEE,
    normaliser,
)

RE_ZONE_PRIVEE = re.compile(f"[{chr(DEBUT_ZONE_PRIVEE)}-{chr(FIN_ZONE_PRIVEE)}]")

# recherche_fts est recalcule PAR POSTGRESQL, avec la meme expression
# qu'a l'insertion (voir 3_charger.inserer_articles) : c'est lui qui
# connait la configuration 'french', pas Python. Un contenu corrige
# laisse avec son ancien index se retrouverait introuvable en recherche
# lexicale sur les mots voisins de la puce.
CORRECTION = text(
    """
    UPDATE article
       SET contenu = :contenu,
           recherche_fts = to_tsvector('french', :contenu)
     WHERE id = :id
    """
)


def articles_a_corriger(session) -> list[dict]:
    """Articles dont le contenu change en passant par normaliser().

    On ne selectionne pas « ceux qui contiennent un glyphe » mais « ceux
    que la normalisation modifie » : c'est la meme fonction que
    l'ingestion, donc le resultat est par construction celui qu'aurait
    produit un rechargement.
    """
    lignes = session.execute(
        text(
            "SELECT a.id, t.sigle, a.numero, a.contenu "
            "FROM article a JOIN texte t ON t.id = a.texte_id"
        )
    ).all()

    a_faire = []
    for identifiant, sigle, numero, contenu in lignes:
        corrige = normaliser(contenu or "")
        if corrige != (contenu or ""):
            a_faire.append(
                {
                    "id": identifiant,
                    "sigle": sigle,
                    "numero": numero,
                    "avant": contenu,
                    "contenu": corrige,
                }
            )
    return a_faire


def apercu(article: dict, marge: int = 45) -> str:
    """Montre le premier passage modifie, dans son contexte."""
    trouve = RE_ZONE_PRIVEE.search(article["avant"])
    position = trouve.start() if trouve else 0
    extrait = article["avant"][max(0, position - marge) : position + marge]
    return " ".join(extrait.split())


def main() -> None:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--appliquer",
        action="store_true",
        help="ecrit les corrections (sans ce drapeau, on ne fait que constater)",
    )
    options = analyseur.parse_args()

    with FabriqueSession() as session:
        a_faire = articles_a_corriger(session)

        if not a_faire:
            print("Aucun article a corriger : le corpus est propre.")
            return

        par_sigle: dict[str, int] = {}
        for article in a_faire:
            par_sigle[article["sigle"]] = par_sigle.get(article["sigle"], 0) + 1

        print(f"{len(a_faire)} article(s) a corriger :")
        for sigle, nombre in sorted(par_sigle.items()):
            print(f"  {sigle:10s} {nombre:4d}")

        print("\nExemples (avant) :")
        for article in a_faire[:3]:
            print(f"  {article['sigle']} art.{article['numero']} : {apercu(article)!r}")

        if not options.appliquer:
            print("\nConstat seul. Relancer avec --appliquer pour corriger.")
            return

        for article in a_faire:
            session.execute(
                CORRECTION, {"id": article["id"], "contenu": article["contenu"]}
            )
        session.commit()
        print(f"\n{len(a_faire)} article(s) corriges, index plein texte recalcule.")

        restants = articles_a_corriger(session)
        print(
            "Verification : corpus propre."
            if not restants
            else f"ATTENTION : {len(restants)} article(s) resistent encore."
        )


if __name__ == "__main__":
    main()
