"""Recupere le Code general des impots aupres de la DGI, et l'OCRise.

POURQUOI CE SCRIPT EXISTE, ALORS QUE LE PIPELINE PART D'UN PDF.
La Direction generale des impots ne publie pas le CGI en PDF, ni en
texte : elle le publie en 1005 IMAGES, une par page, inserees dans une
page web (impots.cm, « CGI mis a jour au 1er janvier 2025 »). Il n'y a
pas d'autre edition officielle en ligne.

La numerotation de ces images va de 0 a 1007 mais COMPORTE DES TROUS
(312, 314, 315 n'existent pas). C'est pourquoi la liste des pages est
lue sur la page elle-meme plutot que deduite d'un intervalle : voir
pages_publiees().

L'impression de cette page par un navigateur — la voie qu'on avait
essayee d'abord — produit un PDF de 2042 pages dont 1776 blanches, avec
des articles manquants et des doublons : le navigateur ne charge pas
toutes les images. Les controles d'ingestion l'avaient refuse, a juste
titre. On va donc chercher les images a la source.

CE QUE CE SCRIPT PRODUIT : exactement le meme contrat de sortie que
1_extraire.py — un fichier texte pagine par des marqueurs ===PAGE n===.
La suite du pipeline (2_decouper, controler, 3_charger) fonctionne
ensuite sans rien savoir de cette origine particuliere.

ON TELECHARGE POLIMENT. Une requete a la fois, avec une pause : c'est un
serveur public d'administration, pas une API prevue pour nous. Le script
est REPRENABLE — une image deja presente n'est pas retelechargee — parce
qu'une coupure au bout de 900 pages ne doit pas coûter les 900.

USAGE
    python ingestion/recuperer_cgi.py                 # tout
    python ingestion/recuperer_cgi.py --pages 0-49    # un echantillon
    python ingestion/recuperer_cgi.py --sans-ocr      # telecharger seulement
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from chemins import DOSSIER_SORTIE, preparer_dossiers

from app.services.extraction import (
    localiser_tesseract,
    nettoyer_pages,
    page_blanche,
    retirer_lignes_parasites,
)

PAGE_SOURCE = (
    "https://www.impots.cm/fr/code-general-des-impots-mis-jour-au-1er-janvier-2025"
)
MOTIF_IMAGE = (
    "https://www.impots.cm/sites/default/files/inline-images/"
    "CGI%202025%20OK-images-{numero}.jpg"
)
DERNIERE_PAGE = 1007

# Un navigateur ordinaire : le site sert des pages differentes, voire
# rien du tout, aux clients qui ne s'annoncent pas.
AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Pause entre deux requetes. Une seconde sur 1008 pages fait 17 minutes
# de telechargement — c'est le prix a payer pour ne pas peser sur un
# serveur public qui ne nous doit rien.
PAUSE = 1.0
TENTATIVES = 3

DOSSIER_IMAGES = DOSSIER_SORTIE / "cgi-images"
NOM_SORTIE = "CGI-2025_fr.txt"


RE_IMAGE_PUBLIEE = re.compile(r"OK-images-(\d+)\.jpg")


def pages_publiees() -> list[int]:
    """Numeros des pages reellement publiees, LUS SUR LA PAGE.

    ON NE SUPPOSE PAS 0..1007. La numerotation de la DGI comporte des
    trous — les images 312, 314 et 315 n'existent pas, et la page ne les
    reference pas davantage. Les demander produisait trois 404 qu'on
    aurait pu prendre pour des pages perdues, alors que le document est
    complet sans elles.

    Lire la liste a la source evite aussi qu'une reedition plus longue
    ou plus courte passe inapercue.
    """
    requete = urllib.request.Request(PAGE_SOURCE, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(requete, timeout=90) as reponse:
        html = reponse.read().decode("utf-8", errors="replace")

    numeros = sorted({int(n) for n in RE_IMAGE_PUBLIEE.findall(html)})
    if not numeros:
        raise RuntimeError(
            "Aucune image trouvee sur la page de la DGI. Sa structure a "
            "probablement change : verifier " + PAGE_SOURCE
        )
    return numeros


def chemin_image(numero: int) -> Path:
    return DOSSIER_IMAGES / f"cgi-{numero:04d}.jpg"


def telecharger_une(numero: int) -> tuple[bool, str]:
    """Recupere une page. Rend (a-t-on l'image, message)."""
    destination = chemin_image(numero)
    if destination.exists() and destination.stat().st_size > 10_000:
        return True, "deja presente"

    requete = urllib.request.Request(
        MOTIF_IMAGE.format(numero=numero), headers={"User-Agent": AGENT}
    )
    for tentative in range(1, TENTATIVES + 1):
        try:
            with urllib.request.urlopen(requete, timeout=60) as reponse:
                octets = reponse.read()
            if len(octets) < 10_000:
                return False, f"reponse trop courte ({len(octets)} octets)"
            destination.write_bytes(octets)
            return True, f"{len(octets) // 1024} Ko"
        except urllib.error.HTTPError as erreur:
            # UN 404 EST DEFINITIF, PAS UN INCIDENT. Certaines pages ne
            # sont tout simplement pas publiees sous ce nom. Les
            # reessayer trois fois avec des pauses croissantes fait
            # perdre du temps sans aucune chance de succes ; pire, cela
            # noie les vraies pannes passageres dans l'attente.
            if erreur.code in (404, 410):
                return False, f"absente du serveur (HTTP {erreur.code})"
            if tentative == TENTATIVES:
                return False, f"HTTP {erreur.code}"
            time.sleep(PAUSE * tentative * 2)
        except (urllib.error.URLError, TimeoutError) as erreur:
            if tentative == TENTATIVES:
                return False, str(erreur)
            # Une panne reseau passagere ne doit pas condamner la page :
            # on patiente un peu plus a chaque essai.
            time.sleep(PAUSE * tentative * 2)
    return False, "echec"


def telecharger(numeros: list[int]) -> list[int]:
    """Telecharge les pages demandees. Rend celles qu'on a reellement."""
    DOSSIER_IMAGES.mkdir(parents=True, exist_ok=True)
    obtenues, manquantes = [], []

    for rang, numero in enumerate(numeros, 1):
        ok, message = telecharger_une(numero)
        if ok:
            obtenues.append(numero)
        else:
            manquantes.append(numero)
            print(f"  page {numero} : ECHEC — {message}", flush=True)

        if message != "deja presente":
            time.sleep(PAUSE)
        if rang % 50 == 0 or rang == len(numeros):
            print(
                f"  ... {rang}/{len(numeros)} pages "
                f"({len(manquantes)} echec(s))",
                flush=True,
            )

    if manquantes:
        # On le dit fort : un CGI incomplet qui entre en base est
        # exactement le defaut qu'on cherche a eviter.
        print(f"\n{len(manquantes)} page(s) manquante(s) : {manquantes[:20]}")
    return obtenues


def ocriser(numeros: list[int]) -> list[tuple[int, str]]:
    """OCR des images recuperees, dans l'ordre des pages."""
    import pytesseract
    from PIL import Image

    binaire = localiser_tesseract()
    if not binaire:
        raise RuntimeError(
            "Tesseract est introuvable. Installe-le, ou renseigne "
            "TESSERACT_CMD avec le chemin du binaire."
        )
    pytesseract.pytesseract.tesseract_cmd = binaire

    pages, blanches = [], 0
    for rang, numero in enumerate(numeros, 1):
        with Image.open(chemin_image(numero)) as image:
            if page_blanche(image):
                blanches += 1
                pages.append((numero, ""))
            else:
                pages.append((numero, pytesseract.image_to_string(image, lang="fra")))

        if rang % 25 == 0 or rang == len(numeros):
            print(
                f"  ... {rang}/{len(numeros)} pages OCRisees "
                f"({blanches} blanche(s))",
                flush=True,
            )
    return pages


def analyser_pages(brut: str) -> list[int]:
    """« 0-49 », « 3 », « 0-9,900-1007 » -> liste de numeros."""
    numeros: list[int] = []
    for morceau in brut.split(","):
        morceau = morceau.strip()
        if "-" in morceau:
            debut, fin = (int(v) for v in morceau.split("-", 1))
            numeros.extend(range(debut, fin + 1))
        else:
            numeros.append(int(morceau))
    return [n for n in numeros if 0 <= n <= DERNIERE_PAGE]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    analyseur = argparse.ArgumentParser(description="Recuperation du CGI (DGI).")
    analyseur.add_argument(
        "--pages",
        help=f"pages a traiter, ex. « 0-49 » (defaut : 0-{DERNIERE_PAGE})",
    )
    analyseur.add_argument(
        "--sans-ocr", action="store_true", help="telecharger sans OCRiser"
    )
    analyseur.add_argument(
        "--sortie", help=f"fichier texte produit (defaut : sortie/{NOM_SORTIE})"
    )
    arguments = analyseur.parse_args()

    preparer_dossiers()
    if arguments.pages:
        numeros = analyser_pages(arguments.pages)
    else:
        # La liste vient de la page elle-meme, pas d'une hypothese sur
        # sa longueur : voir pages_publiees().
        numeros = pages_publiees()

    print(f"Source : {PAGE_SOURCE}")
    print(f"{len(numeros)} page(s) a recuperer, une requete toutes les {PAUSE} s")
    obtenues = telecharger(numeros)
    print(f"\n{len(obtenues)}/{len(numeros)} image(s) disponibles.")

    if arguments.sans_ocr or not obtenues:
        return 0 if obtenues else 1

    print("\nOCR (francais)")
    pages = ocriser(obtenues)

    # LE MEME NETTOYAGE QUE POUR UN PDF. L'OCR lit aussi le titre courant
    # et le folio imprimes sur chaque page : sans cette etape, ils se
    # retrouvent colles dans le contenu des articles.
    brutes, diagnostic = nettoyer_pages([texte for _, texte in pages])
    brutes, parasites = retirer_lignes_parasites(brutes)
    diagnostic["lignes_parasites_retirees"] = parasites

    destination = Path(arguments.sortie) if arguments.sortie else DOSSIER_SORTIE / NOM_SORTIE
    with destination.open("w", encoding="utf-8") as fichier:
        for numero, texte in enumerate(brutes, 1):
            fichier.write(f"\n===PAGE {numero}===\n{texte}")

    non_vides = [t for t in brutes if t.strip()]
    print(f"\nTexte ecrit : {destination}")
    print(f"  Pages            : {len(brutes)}")
    print(f"  Pages vides      : {len(brutes) - len(non_vides)}")
    print(
        "  Caracteres/page  : "
        f"{sum(len(t) for t in non_vides) / max(1, len(non_vides)):.0f} "
        "en moyenne (pages non vides)"
    )
    for cle, valeur in diagnostic.items():
        print(f"  {cle:24s} : {valeur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
