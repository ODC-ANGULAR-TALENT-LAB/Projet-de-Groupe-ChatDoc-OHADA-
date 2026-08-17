"""B.1 - Collecte et tracabilite.

Enregistre la fiche de provenance d'un PDF officiel : d'ou il vient,
quand il a ete telecharge, et son empreinte SHA-256. C'est ce qui
permettra, dans six mois, de savoir exactement quelle version a ete
ingeree - et de remonter toute reponse contestee a sa source exacte.

A lancer AVANT toute extraction, depuis le dossier backend/ :

    python ingestion/0_provenance.py sources/auscgie_2014.pdf \\
        --url "https://www.ohada.org/..." \\
        --sigle AUSCGIE \\
        --titre "Acte uniforme relatif au droit des societes commerciales et du GIE" \\
        --version "revision 2014" \\
        --date-consolidation 2014-05-05 \\
        --valide-par Christian

Produit : sources/auscgie_2014.provenance.json
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

from chemins import DOSSIER_SOURCES, preparer_dossiers

# Lecture par blocs : un PDF de plusieurs centaines de pages n'a aucune
# raison d'etre charge entierement en memoire.
TAILLE_BLOC = 1024 * 1024


def empreinte_sha256(chemin: Path) -> str:
    """Empreinte SHA-256 de la source, calculee en flux.

    LA SOURCE N'EST PAS TOUJOURS UN FICHIER. La Direction generale des
    impots ne publie pas le Code general des impots en PDF : elle le
    publie en 1008 IMAGES, une par page. Empreindre un dossier revient
    alors a empreindre le document — a condition de lire les pages DANS
    L'ORDRE, sinon l'empreinte changerait d'une machine a l'autre selon
    le classement du systeme de fichiers, et ne prouverait plus rien.
    """
    condensat = hashlib.sha256()
    fichiers = sorted(p for p in chemin.iterdir() if p.is_file()) if chemin.is_dir() else [chemin]
    for fichier in fichiers:
        with fichier.open("rb") as flux:
            for bloc in iter(lambda: flux.read(TAILLE_BLOC), b""):
                condensat.update(bloc)
    return condensat.hexdigest()


def taille_octets(chemin: Path) -> int:
    """Poids de la source, dossier de pages compris."""
    if chemin.is_dir():
        return sum(p.stat().st_size for p in chemin.iterdir() if p.is_file())
    return chemin.stat().st_size


def ecrire_fiche(chemin_pdf: Path, champs: dict, destination: Path | None = None) -> Path:
    """Ecrit la fiche de provenance a cote de la source.

    `destination` sert quand la source ne peut PAS heberger sa fiche.
    Les 1008 images du CGI vivent dans ingestion/sortie/, entierement
    ignore par Git ; la fiche, elle, doit etre suivie — c'est la seule
    piece qui dit d'ou vient le texte. Elle va donc dans sources/, sous
    le nom que 2_decouper.py sait deduire du fichier texte.
    """
    fiche = {
        "fichier": chemin_pdf.name,
        "sigle": champs["sigle"],
        "titre": champs["titre"],
        "type": champs["type"],
        "version": champs["version"],
        "date_consolidation": champs["date_consolidation"],
        "url_source": champs["url"],
        "telecharge_le": datetime.date.today().isoformat(),
        "sha256": empreinte_sha256(chemin_pdf),
        "taille_octets": taille_octets(chemin_pdf),
        "valide_par": champs["valide_par"],
    }

    if destination is None:
        destination = (
            chemin_pdf.with_name(chemin_pdf.name + ".provenance.json")
            if chemin_pdf.is_dir()
            else chemin_pdf.with_suffix(".provenance.json")
        )
    destination.write_text(
        json.dumps(fiche, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Fiche de provenance d'un texte officiel (B.1)."
    )
    analyseur.add_argument(
        "pdf",
        help="chemin du PDF officiel, ou du dossier de pages quand "
        "l'editeur ne publie pas de PDF (cas du CGI)",
    )
    analyseur.add_argument(
        "--url", required=True, help="URL officielle exacte du telechargement"
    )
    analyseur.add_argument("--sigle", required=True, help="AUSCGIE, CGI, CIMA...")
    analyseur.add_argument("--titre", required=True, help="intitule complet du texte")
    analyseur.add_argument(
        "--type",
        default="acte_uniforme",
        choices=["acte_uniforme", "code"],
        help="nature du texte (defaut : acte_uniforme)",
    )
    analyseur.add_argument(
        "--version", required=True, help='ex. "revision 2014", "LF 2026"'
    )
    analyseur.add_argument(
        "--date-consolidation",
        required=True,
        help="date de la version consolidee, format AAAA-MM-JJ",
    )
    analyseur.add_argument(
        "--valide-par", required=True, help="qui repond de cette ingestion"
    )
    analyseur.add_argument(
        "--fiche",
        help="ou ecrire la fiche (defaut : a cote de la source). Utile "
        "quand la source vit dans un dossier ignore par Git.",
    )
    return analyseur.parse_args()


def main() -> int:
    arguments = analyser_arguments()
    preparer_dossiers()

    chemin_pdf = Path(arguments.pdf)
    if not chemin_pdf.is_absolute():
        # Chemin relatif : d'abord tel quel, puis dans sources/.
        if not chemin_pdf.exists():
            chemin_pdf = DOSSIER_SOURCES / chemin_pdf.name

    if not chemin_pdf.exists():
        print(f"ERREUR : source introuvable -> {arguments.pdf}", file=sys.stderr)
        print(
            f"         depose le PDF officiel dans {DOSSIER_SOURCES}, ou "
            "indique le dossier des pages",
            file=sys.stderr,
        )
        return 1

    try:
        datetime.date.fromisoformat(arguments.date_consolidation)
    except ValueError:
        print(
            "ERREUR : --date-consolidation attend le format AAAA-MM-JJ",
            file=sys.stderr,
        )
        return 1

    fiche = ecrire_fiche(
        chemin_pdf,
        {
            "url": arguments.url,
            "sigle": arguments.sigle,
            "titre": arguments.titre,
            "type": arguments.type,
            "version": arguments.version,
            "date_consolidation": arguments.date_consolidation,
            "valide_par": arguments.valide_par,
        },
        Path(arguments.fiche) if arguments.fiche else None,
    )

    contenu = json.loads(fiche.read_text(encoding="utf-8"))
    print(f"Fiche de provenance ecrite : {fiche}")
    print(f"  SHA-256 : {contenu['sha256']}")
    print(f"  Taille  : {contenu['taille_octets']:,} octets".replace(",", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
