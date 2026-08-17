"""B.2 - Extraction du texte.

Deux cas. Si le PDF contient du texte natif, pdfplumber suffit et le
resultat est propre. Si le PDF est un scan, il faut passer par l'OCR :
plus lent, et surtout plus risque.

A lancer depuis le dossier backend/ :

    python ingestion/1_extraire.py sources/auscgie_2014.pdf

Produit : ingestion/sortie/auscgie_2014.txt, pagine par des marqueurs
===PAGE n=== que le decoupage (2_decouper.py) sait reconnaitre.

APRES UN OCR, RELIS TOUJOURS UN ECHANTILLON A L'OEIL. L'OCR confond
regulierement 0/O, 1/l, 5/S - or dans un texte juridique, un numero
d'article ou un taux errone est bien pire qu'une absence d'information.
Si l'OCR est trop sale, cherche une meilleure source plutot que de
corriger a la main.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chemins import DOSSIER_SORTIE, DOSSIER_SOURCES, preparer_dossiers

from app.services.extraction import (
    extraire,
    localiser_tesseract,
    nettoyer_pages,
    page_blanche,
    retirer_lignes_parasites,
)

# En dessous de cette moyenne de caracteres par page, le PDF est
# considere comme scanne : il n'y a pas de couche de texte a extraire.
SEUIL_PAGE_SCANNEE = 100


def extraire_texte_natif(chemin_pdf: Path) -> tuple[list[tuple[int, str]], dict]:
    """Extrait la couche de texte du PDF, page par page.

    Delegue a app/services/extraction.py, PARTAGE AVEC LE BACK-OFFICE :
    un PDF depose par l'administrateur et un PDF passe en ligne de
    commande doivent produire exactement le meme texte. Une extraction
    naive (pdfplumber seul) laisse passer trois defauts que ce module
    corrige — colonnes entrelacees, en-tetes absorbes dans les articles,
    mots coupes en fin de ligne.
    """
    return extraire(chemin_pdf.read_bytes())


# Ecart entre canaux au-dela duquel un pixel est tenu pour colore.
# 45 sur 255 : large pour ne pas mordre sur le noir d'imprimerie, qui
# n'est jamais parfaitement neutre apres numerisation, et suffisant pour
# attraper l'encre bleue d'un stylo.
SEUIL_COULEUR = 45


def retirer_encre_manuscrite(image, seuil: int = SEUIL_COULEUR):
    """Blanchit les pixels colores : paraphes, tampons, annotations.

    LE JOURNAL OFFICIEL EST PARAPHE A LA MAIN. L'exemplaire de l'AUPSRVE
    porte, au bas de chacune de ses pages, les initiales manuscrites des
    ministres signataires. Tesseract les lit comme du texte et produit du
    charabia — « À HE Lao 6 BHA AN ° » — qui s'insere AU MILIEU d'un
    article, a l'endroit de la coupure de page. Mesure sur ce document :
    85 articles pollues sur 445.

    Ce n'est pas cosmetique. L'extrait est montre a l'utilisateur comme
    le texte officiel, et il part tel quel a la vectorisation.

    On separe a la couleur, pas a la position : les paraphes debordent
    dans la zone de texte et une bande fixe en couperait de vrais
    alineas. Le texte imprime est noir, donc neutre — ses trois canaux
    sont proches ; une encre de stylo ne l'est jamais.
    """
    from PIL import Image, ImageChops

    rouge, vert, bleu = image.convert("RGB").split()
    haut = ImageChops.lighter(ImageChops.lighter(rouge, vert), bleu)
    bas = ImageChops.darker(ImageChops.darker(rouge, vert), bleu)
    colore = ImageChops.difference(haut, bas).point(
        lambda valeur: 255 if valeur > seuil else 0
    )
    blanc = Image.new("L", image.size, 255)
    return Image.composite(blanc, image.convert("L"), colore.convert("1"))


def extraire_par_ocr(
    chemin_pdf: Path, dpi: int, sans_annotations: bool = False
) -> list[tuple[int, str]]:
    """Rend le PDF en images puis lit chaque image avec Tesseract.

    UNE PAGE A LA FOIS. Rendre tout le document d'un coup paraissait plus
    simple, mais une page A4 a 300 dpi pese une trentaine de mega-octets
    une fois decompressee : sur le Journal officiel de l'AUPSRVE, 122
    pages, cela demandait plus de trois giga-octets de memoire vive avant
    le moindre caractere reconnu. On rend, on lit, on jette.

    Le rendu passe par pypdfium2, deja installe avec pdfplumber, plutot
    que par pdf2image : ce dernier appelle poppler, un binaire externe
    supplementaire a installer et a mettre dans le PATH sous Windows.
    """
    try:
        import pypdfium2
        import pytesseract
    except ImportError as erreur:
        raise RuntimeError(
            "OCR indisponible : " + str(erreur) + "\n"
            "Installe les dependances : pip install -r requirements.txt"
        ) from erreur

    binaire = localiser_tesseract()
    if binaire is None:
        raise RuntimeError(
            "Tesseract est introuvable.\n"
            "Sur Windows : winget install UB-Mannheim.TesseractOCR\n"
            "Le pack de langue francaise ne vient PAS avec l'installeur : "
            "depose fra.traineddata dans le dossier tessdata/, puis\n"
            "verifie avec : tesseract --list-langs"
        )
    pytesseract.pytesseract.tesseract_cmd = binaire

    document = pypdfium2.PdfDocument(str(chemin_pdf))
    total = len(document)
    print(f"  OCR de {total} pages a {dpi} dpi (long)...", flush=True)

    pages: list[tuple[int, str]] = []
    blanches = 0
    try:
        for numero in range(1, total + 1):
            page = document[numero - 1]
            # pypdfium2 raisonne en facteur d'echelle, pas en dpi : un PDF
            # est defini a 72 points par pouce.
            rendu = page.render(scale=dpi / 72)
            image = rendu.to_pil()

            # Page blanche : on ne paie pas l'OCR. La page reste dans la
            # liste, vide — la numerotation doit rester celle du PDF,
            # sans quoi les pages annoncees a la relecture ne
            # correspondraient plus au document.
            if page_blanche(image):
                pages.append((numero, ""))
                blanches += 1
                image.close()
                page.close()
                continue

            if sans_annotations:
                image = retirer_encre_manuscrite(image)
            try:
                texte = pytesseract.image_to_string(image, lang="fra")
            except pytesseract.TesseractError as erreur:
                raise RuntimeError(
                    "Tesseract a refuse la langue « fra ».\n"
                    "Le pack francais manque : depose fra.traineddata dans "
                    "le dossier tessdata/ de Tesseract.\n"
                    "Detail : " + str(erreur)
                ) from erreur
            pages.append((numero, texte))
            image.close()
            page.close()
            if numero % 25 == 0 or numero == total:
                print(
                    f"  ... {numero}/{total} pages "
                    f"({blanches} blanche(s) sautee(s))",
                    flush=True,
                )
    finally:
        document.close()

    if blanches:
        print(f"  {blanches} page(s) blanche(s) non OCRisees.", flush=True)
    return pages


def ecrire_texte(pages: list[tuple[int, str]], destination: Path) -> None:
    """Ecrit le texte pagine, un marqueur par page."""
    with destination.open("w", encoding="utf-8") as fichier:
        for numero, texte in pages:
            fichier.write(f"\n===PAGE {numero}===\n{texte}")


def analyser_arguments() -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Extraction du texte d'un PDF officiel (B.2)."
    )
    analyseur.add_argument("pdf", help="chemin du PDF officiel")
    analyseur.add_argument(
        "--sortie",
        help="fichier texte produit (defaut : ingestion/sortie/<nom>.txt)",
    )
    analyseur.add_argument(
        "--force-ocr",
        action="store_true",
        help="forcer l'OCR meme si une couche de texte est detectee",
    )
    analyseur.add_argument(
        "--dpi", type=int, default=300, help="resolution du rendu OCR (defaut : 300)"
    )
    analyseur.add_argument(
        "--sans-annotations",
        action="store_true",
        help="blanchir l'encre coloree avant l'OCR : paraphes manuscrits, "
        "tampons. A utiliser sur un exemplaire signe a la main.",
    )
    return analyseur.parse_args()


def main() -> int:
    # La console Windows est en cp1252 : afficher une ligne du document
    # telle quelle (tirets typographiques, guillemets) fait echouer le
    # script sur un UnicodeEncodeError, apres un travail d'extraction
    # deja fait. Le diagnostic ne doit jamais couter le resultat.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    arguments = analyser_arguments()
    preparer_dossiers()

    chemin_pdf = Path(arguments.pdf)
    if not chemin_pdf.is_absolute() and not chemin_pdf.exists():
        chemin_pdf = DOSSIER_SOURCES / chemin_pdf.name

    if not chemin_pdf.exists():
        print(f"ERREUR : fichier introuvable -> {arguments.pdf}", file=sys.stderr)
        print(f"         depose le PDF officiel dans {DOSSIER_SOURCES}", file=sys.stderr)
        return 1

    fiche = chemin_pdf.with_suffix(".provenance.json")
    if not fiche.exists():
        print(
            "ERREUR : aucune fiche de provenance pour ce PDF.\n"
            "         Lance d'abord ingestion/0_provenance.py : on n'ingere "
            "jamais un PDF dont on ne sait pas d'ou il vient.",
            file=sys.stderr,
        )
        return 1

    destination = (
        Path(arguments.sortie)
        if arguments.sortie
        else DOSSIER_SORTIE / (chemin_pdf.stem + ".txt")
    )

    print(f"Lecture de {chemin_pdf.name}")
    pages, diagnostic = extraire_texte_natif(chemin_pdf)

    if not pages:
        print("ERREUR : le PDF ne contient aucune page.", file=sys.stderr)
        return 1

    moyenne = sum(len(texte) for _, texte in pages) / len(pages)
    scanne = moyenne < SEUIL_PAGE_SCANNEE

    if arguments.force_ocr or scanne:
        raison = "demande explicite" if arguments.force_ocr else "PDF scanne detecte"
        print(f"OCR ({raison}, moyenne {moyenne:.0f} caracteres par page)")
        try:
            pages = extraire_par_ocr(
                chemin_pdf, arguments.dpi, arguments.sans_annotations
            )
        except RuntimeError as erreur:
            print(f"ERREUR : {erreur}", file=sys.stderr)
            return 1

        # LE MEME NETTOYAGE QUE POUR UN PDF NATIF. L'OCR lit aussi le
        # titre courant et le folio imprimes sur chaque page : sans cette
        # etape, ils se retrouvent colles dans le contenu des articles.
        brutes, diagnostic = nettoyer_pages([texte for _, texte in pages])

        # PUIS le bruit propre a l'OCR : traits, paraphes, plis de
        # reliure rendus en glyphes. Reserve au chemin OCR — sur un PDF
        # natif, ces caracteres ne se produisent pas.
        brutes, parasites = retirer_lignes_parasites(brutes)
        diagnostic["lignes_parasites_retirees"] = parasites

        pages = list(enumerate(brutes, 1))
        moyenne = sum(len(texte) for _, texte in pages) / len(pages)

    ecrire_texte(pages, destination)

    vides = sum(1 for _, texte in pages if not texte.strip())
    print()
    print(f"Texte ecrit : {destination}")
    print(f"  Pages            : {len(pages)}")
    print(f"  Caracteres/page  : {moyenne:.0f} en moyenne")
    print(f"  Pages vides      : {vides}")

    # Le diagnostic de mise en page n'est pas decoratif : savoir qu'un
    # document etait sur deux colonnes, ou combien de lignes repetees ont
    # ete retirees, change la facon dont on relit le decoupage ensuite.
    if diagnostic:
        colonnes = diagnostic.get("pages_deux_colonnes", 0)
        if colonnes:
            print(f"  Pages 2 colonnes : {colonnes}")
        print(f"  Cesures recollees: {diagnostic.get('cesures_recollees', 0)}")
        repetees = diagnostic.get("lignes_repetees_retirees") or []
        print(f"  Lignes repetees  : {len(repetees)} retirees")
        for ligne in repetees[:3]:
            print(f"      - {ligne[:70]}")
    if scanne or arguments.force_ocr:
        print()
        print("  Texte issu d'un OCR : relis un echantillon a l'oeil AVANT")
        print("  de decouper. Verifie en priorite les numeros d'articles,")
        print("  les taux et les delais.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
