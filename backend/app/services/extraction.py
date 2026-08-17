"""Extraction du texte d'un PDF, mise en page comprise.

DEUX DEFAUTS QUE CE MODULE CORRIGE, ET POURQUOI ILS COMPTENT.

1. LES MISES EN PAGE SUR DEUX COLONNES. Beaucoup d'editions de textes
   juridiques sont composees sur deux colonnes. Une extraction naive
   lit chaque ligne de bout en bout et entrelace les colonnes :

       "peuvent etre augmentes sans le consentement de Art.77.- L'action
        aux fins de regularisation"

   Deux articles differents, fusionnes. Le decoupage produit alors des
   articles dont le contenu appartient au voisin — un corpus qui A L'AIR
   correct et qui ne l'est pas. C'est le pire defaut possible pour ce
   produit : il ne se voit qu'en relisant, article par article.

2. LES EN-TETES ET PIEDS DE PAGE. Titre du document, URL de l'editeur,
   numero de page se retrouvent absorbes dans le contenu de l'article
   qui chevauche la coupure. Ils polluent l'extrait montre a
   l'utilisateur comme "texte officiel", et l'embedding avec.
"""

from __future__ import annotations

import io
import logging
import re
from collections import Counter

import pdfplumber

from app.services.decoupage import normaliser

journal = logging.getLogger(__name__)

# Largeur minimale, en points, d'une gouttiere entre deux colonnes.
# En dessous, c'est une espace entre deux mots, pas une separation.
GOUTTIERE_MINIMALE = 18

# La gouttiere est cherchee dans cette zone centrale de la page : une
# marge laterale large n'est pas une separation de colonnes.
ZONE_CENTRALE = (0.35, 0.65)

# Une ligne presente sur au moins cette part des pages est un en-tete
# ou un pied de page, pas du contenu. Le seuil est bas a dessein : un
# pied de page peut ne figurer que sur les pages impaires, ou disparaitre
# des pages denses. Une phrase de contenu, elle, ne se repete pas sur un
# tiers d'un texte juridique.
PART_REPETITION = 0.3

# En dessous de ce nombre de pages, la detection par repetition n'est
# pas fiable : trop peu d'echantillons.
PAGES_MINIMALES_REPETITION = 4


def _detecter_gouttiere(mots: list[dict], largeur: float) -> float | None:
    """Cherche une bande verticale sans aucun mot, au centre de la page.

    Renvoie l'abscisse de separation, ou None si la page est sur une
    seule colonne.
    """
    if len(mots) < 20:
        return None

    gauche, droite = ZONE_CENTRALE[0] * largeur, ZONE_CENTRALE[1] * largeur

    # Pour chaque abscisse candidate, verifie qu'aucun mot ne la
    # chevauche. On echantillonne tous les 2 points : suffisant pour
    # une gouttiere de 18 points, et bien plus rapide qu'au point pres.
    candidates = []
    x = gauche
    while x <= droite:
        if not any(mot["x0"] < x < mot["x1"] for mot in mots):
            candidates.append(x)
        x += 2

    if not candidates:
        return None

    # Retient la plus large bande continue de candidates.
    meilleure_debut = debut = candidates[0]
    meilleure_fin = fin = candidates[0]
    for valeur in candidates[1:]:
        if valeur - fin <= 2:
            fin = valeur
        else:
            if fin - debut > meilleure_fin - meilleure_debut:
                meilleure_debut, meilleure_fin = debut, fin
            debut = fin = valeur
    if fin - debut > meilleure_fin - meilleure_debut:
        meilleure_debut, meilleure_fin = debut, fin

    if meilleure_fin - meilleure_debut < GOUTTIERE_MINIMALE:
        return None

    separation = (meilleure_debut + meilleure_fin) / 2

    # Une vraie mise en page sur deux colonnes repartit le texte des
    # deux cotes. Si un cote est quasi vide, c'est une marge, pas une
    # colonne.
    a_gauche = sum(1 for mot in mots if mot["x1"] <= separation)
    a_droite = len(mots) - a_gauche
    if min(a_gauche, a_droite) < len(mots) * 0.2:
        return None

    return separation


def _lignes_depuis_mots(mots: list[dict], tolerance: float = 3.0) -> list[str]:
    """Regroupe des mots en lignes, de haut en bas."""
    if not mots:
        return []

    lignes: list[list[dict]] = []
    for mot in sorted(mots, key=lambda m: (round(m["top"], 1), m["x0"])):
        if lignes and abs(lignes[-1][0]["top"] - mot["top"]) <= tolerance:
            lignes[-1].append(mot)
        else:
            lignes.append([mot])

    return [
        " ".join(mot["text"] for mot in sorted(ligne, key=lambda m: m["x0"]))
        for ligne in lignes
    ]


def extraire_page(page) -> tuple[str, bool]:
    """Texte d'une page, colonnes respectees. Signale les deux colonnes."""
    mots = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not mots:
        return "", False

    separation = _detecter_gouttiere(mots, page.width)
    if separation is None:
        return "\n".join(_lignes_depuis_mots(mots)), False

    # Colonne de gauche entierement, PUIS colonne de droite : c'est
    # l'ordre de lecture reel.
    gauche = [mot for mot in mots if mot["x1"] <= separation]
    droite = [mot for mot in mots if mot["x0"] >= separation]
    lignes = _lignes_depuis_mots(gauche) + _lignes_depuis_mots(droite)
    return "\n".join(lignes), True


# Numero de page isole, en tete ou en fin de ligne. Un pied de page le
# porte presque toujours : "Acte uniforme ... general 28" puis "... 29".
# Comparees telles quelles, ces deux lignes sont differentes et AUCUNE
# n'atteint le seuil de repetition — le pied de page traverse alors tout
# le filtre. C'est ce qui laissait passer 20% des articles pollues.
# Le numero de page ne se retire pas par sa position : selon la page,
# l'extraction le rend detache ("...economique 11"), soude au dernier
# mot ("...economique1 1"), ou INSERE DEDANS ("...economiqu2e" pour la
# page 2xx). Une seule regle couvre les trois : la cle de comparaison
# ignore tous les chiffres.
#
# La cle ne sert qu'a rapprocher deux lignes ; le texte conserve, lui,
# n'est jamais modifie.
RE_CHIFFRES = re.compile(r"\d+")

# En dessous de cette longueur, une ligne garde ses chiffres. Sans ce
# garde-fou, "Article 1", "Article 2", "Article 3" se ramenent tous a
# "Article", se comptent comme une ligne repetee, et le filtre efface
# les en-tetes d'articles du document.
#
# Le critere est la LONGUEUR, pas le nombre de mots : le pied de page de
# l'AUPC est "http://...passif.html page 2 / 122", soit trois mots
# seulement — l'URL entiere n'en compte qu'un — pour 143 caracteres. Un
# seuil en mots l'aurait laisse passer sur 121 articles.
LONGUEUR_MINIMALE_REPETITION = 20

# Nombre de lignes examinees en haut et en bas de chaque page. Trois
# suffisent : les editions observees portent au plus deux lignes de
# pied de page (titre de l'acte, puis adresse de l'editeur).
LIGNES_BORD = 3


def _cle_repetition(ligne: str) -> str:
    """Forme comparable d'une ligne, numero de page mis a part.

    Sans cette normalisation, un pied de page numerote est different a
    chaque page et n'est jamais reconnu comme repete.
    """
    propre = ligne.strip()
    if len(propre) < LONGUEUR_MINIMALE_REPETITION:
        return propre
    return " ".join(RE_CHIFFRES.sub("", propre).split())


# Signature laissee par la bibliotheque qui a fabrique le PDF. Elle
# n'apparait qu'UNE FOIS, en fin de document : la detection par
# repetition ne peut pas la voir, par construction. Sans ce filtre, elle
# se retrouve collee au dernier article — "Powered by TCPDF" a la suite
# de l'article 258 de l'AUPC, montre a l'utilisateur comme texte
# officiel.
RE_SIGNATURE_GENERATEUR = re.compile(
    r"^\s*(?:powered by|generated by|created (?:with|by))\s+"
    r"(?:tcpdf|fpdf|itext|dompdf|wkhtmltopdf|pdfkit|reportlab)\b",
    re.I,
)


def _lignes_de_bord(page: str) -> set[int]:
    """Indices des lignes situees en haut ou en bas de la page.

    UN EN-TETE EST TOUJOURS AU BORD. Cette contrainte de position est
    indispensable des lors que la cle ignore les chiffres : sans elle,
    deux lignes de contenu ne differant que par un nombre se confondent,
    et une phrase du texte de loi pourrait etre prise pour un en-tete.
    Une ligne au milieu de la page n'est jamais retiree.
    """
    # Les lignes vides ne comptent pas : une seule ligne blanche en fin
    # de page suffirait sinon a repousser le pied de page hors de la
    # fenetre, et il traverserait le filtre.
    pleines = [
        numero for numero, ligne in enumerate(page.splitlines()) if ligne.strip()
    ]
    return set(pleines[:LIGNES_BORD]) | set(pleines[-LIGNES_BORD:])


def reperer_repetitions(pages: list[str]) -> set[str]:
    """Lignes de bord presentes sur assez de pages pour etre des en-tetes.

    Renvoie des CLES normalisees (voir _cle_repetition), pas les lignes
    brutes : c'est la seule facon de reconnaitre un pied de page dont
    seul le numero change d'une page a l'autre.
    """
    if len(pages) < PAGES_MINIMALES_REPETITION:
        return set()

    compte: Counter[str] = Counter()
    for page in pages:
        bords = _lignes_de_bord(page)
        # set() : une ligne comptee une fois par page, meme si elle y
        # apparait plusieurs fois.
        cles = {
            _cle_repetition(ligne)
            for numero, ligne in enumerate(page.splitlines())
            if numero in bords and ligne.strip()
        }
        for cle in cles:
            if cle:
                compte[cle] += 1

    seuil = max(2, int(len(pages) * PART_REPETITION))
    return {ligne for ligne, n in compte.items() if n >= seuil}


def retirer_repetitions(page: str, repetees: set[str]) -> str:
    """Retire les en-tetes, pieds de page et signatures de generateur."""
    bords = _lignes_de_bord(page)
    return "\n".join(
        ligne
        for numero, ligne in enumerate(page.splitlines())
        if not RE_SIGNATURE_GENERATEUR.match(ligne)
        and (numero not in bords or _cle_repetition(ligne) not in repetees)
    )


# Une lettre suivie d'un trait d'union en fin de ligne : coupure de mot
# en fin de ligne, ou vrai mot compose qui tombe la par hasard.
RE_FIN_COUPEE = re.compile(r"([A-Za-zÀ-ÿ]{2,})-$")
RE_DEBUT_SUITE = re.compile(r"^([a-zà-ÿ]+)(.*)$", re.S)

# Un mot entier du document : ni precede ni suivi d'un trait d'union.
RE_MOT_ENTIER = re.compile(r"(?<![-\w])[A-Za-zÀ-ÿ]{2,}(?![-\w])")
RE_MOT_COMPOSE = re.compile(r"[A-Za-zÀ-ÿ]+-[A-Za-zÀ-ÿ]+")

# Filet de securite quand le document ne tranche pas lui-meme. Ces
# morphemes ne s'ecrivent jamais souds en francais : "non-commercantes"
# ne devient pas "noncommercantes", "main-d'oeuvre" pas "maindoeuvre".
# La liste reste courte a dessein — le document est un bien meilleur juge
# qu'une liste ecrite d'avance, elle ne sert que pour les rares mots qui
# n'apparaissent nulle part ailleurs entiers.
GAUCHES_A_TRAIT = {
    "ci", "non", "main", "sous", "demi", "semi", "mi", "quasi", "ex",
    "vis", "au", "par", "contre", "avant", "apres", "nu", "grand",
    "celui", "celle", "ceux", "celles", "lui", "elle", "elles", "eux", "soi",
}
DROITES_A_TRAIT = {
    "ci", "la", "meme", "memes", "même", "mêmes", "ce", "il", "ils",
    "elle", "elles", "on", "vous", "nous", "y", "dessus", "dessous",
    "apres", "après", "joint", "jointe", "contre", "delà", "dela",
}


def _vocabulaire(pages: list[str]) -> tuple[set[str], set[str]]:
    """Mots entiers et mots composes attestes dans le document.

    LE DOCUMENT EST SON PROPRE DICTIONNAIRE. C'est ce qui permet de
    trancher sans ressource externe, et avec le vocabulaire juridique
    exact du texte plutot qu'avec un lexique general.
    """
    entier = " ".join(pages)
    return (
        {mot.lower() for mot in RE_MOT_ENTIER.findall(entier)},
        {mot.lower() for mot in RE_MOT_COMPOSE.findall(entier)},
    )


def _arbitrer(
    gauche: str, droite: str, entiers: set[str], composes: set[str]
) -> str:
    """Faut-il souder les deux moitieds, ou garder le trait d'union ?

    L'arbitrage est le meme quelle que soit l'origine de la coupure —
    fin de ligne ou espace parasite au fil du texte. C'est pourquoi il
    vit ici plutot que d'etre recopie aux deux endroits : deux regles
    qui divergeraient produiraient deux orthographes du meme mot dans le
    meme corpus.
    """
    soude, compose = (gauche + droite).lower(), f"{gauche}-{droite}".lower()

    if soude in entiers:
        return gauche + droite
    if compose in composes:
        return f"{gauche}-{droite}"
    if gauche.lower() in GAUCHES_A_TRAIT or droite.lower() in DROITES_A_TRAIT:
        return f"{gauche}-{droite}"
    # Par defaut on soude : sur ce corpus, les coupures typographiques
    # sont vingt fois plus nombreuses que les mots composes.
    return gauche + droite


# Trait d'union suivi d'une espace AU FIL D'UNE LIGNE. Rien a voir avec
# une coupure de fin de ligne : l'extraction PDF rend "juge-commissaire"
# comme deux mots, "juge-" et "commissaire", que le regroupement en
# lignes recolle avec une espace. Mesure sur l'AUPC : 36 occurrences,
# toutes sur des termes de procedure — "juge- commissaire", "ci- dessus".
RE_COUPE_INTERNE = re.compile(r"([A-Za-zÀ-ÿ]{2,})- ([a-zà-ÿ]+)")


def recoller_dans_la_ligne(
    ligne: str, entiers: set[str], composes: set[str]
) -> tuple[str, int]:
    """Repare les mots separes par une espace apres le trait d'union."""
    nombre = 0

    def remplacer(trouve: re.Match) -> str:
        nonlocal nombre
        nombre += 1
        return _arbitrer(trouve.group(1), trouve.group(2), entiers, composes)

    return RE_COUPE_INTERNE.sub(remplacer, ligne), nombre


def recoller_cesures(pages: list[str]) -> tuple[list[str], int]:
    """Repare les mots coupes en fin de ligne.

    UN TRAIT D'UNION EN FIN DE LIGNE EST AMBIGU. Dans "commercia-/les"
    il faut le supprimer ; dans "ci-/dessus" il faut le garder. Les
    traiter de la meme facon casse un cas ou l'autre.

    On tranche en interrogeant le document : si la forme soudee est
    attestee ailleurs, c'etait une coupure ; si la forme a trait d'union
    l'est, le trait appartient au mot.

    L'enjeu n'est pas cosmetique. "commercia- les" est indexe par la
    recherche plein texte comme deux jetons, "commercia" et "les" : une
    recherche sur "commerciales" ne trouve pas l'article. Et l'extrait
    montre a l'utilisateur comme texte officiel porte alors une faute
    qui n'existe pas dans le Journal Officiel.
    """
    # NORMALISER D'ABORD. Les editions juridiques composent la coupure
    # avec U+2010, pas avec le tiret-moins du clavier : sans cette
    # etape, l'AUSCGIE ne montre aucune cesure a reparer alors qu'il en
    # compte des dizaines. Meme normalisation qu'au decoupage, pour que
    # les deux etapes voient exactement le meme texte.
    pages = [normaliser(page) for page in pages]
    entiers, composes = _vocabulaire(pages)

    # Le document est traite d'un seul tenant : une coupure peut
    # enjamber une fin de page, et c'est justement la que le texte est
    # le plus abime.
    lignes: list[str] = []
    frontieres: list[int] = []
    for page in pages:
        lignes.extend(page.splitlines())
        frontieres.append(len(lignes))

    recollees = 0
    index = 0
    while index < len(lignes) - 1:
        coupe = RE_FIN_COUPEE.search(lignes[index].rstrip())
        if not coupe:
            index += 1
            continue

        # La suite est sur la prochaine ligne non vide.
        suivant = index + 1
        while suivant < len(lignes) and not lignes[suivant].strip():
            suivant += 1
        if suivant >= len(lignes):
            break

        suite = RE_DEBUT_SUITE.match(lignes[suivant].lstrip())
        if not suite:
            index += 1
            continue

        gauche, droite, reste = coupe.group(1), suite.group(1), suite.group(2)
        jonction = _arbitrer(gauche, droite, entiers, composes)

        # La suite de la ligne remonte AVEC le mot repare. La laisser en
        # dessous la ferait recoller par un espace au decoupage, et la
        # ponctuation se detacherait : "ci-dessus , la clause".
        lignes[index] = lignes[index].rstrip()[: coupe.start()] + jonction + reste
        lignes[suivant] = ""
        recollees += 1
        # On ne bouge pas : la ligne reparee peut se terminer par une
        # nouvelle coupure.

    # Second passage, AU FIL DES LIGNES cette fois : le trait d'union
    # suivi d'une espace ne vient pas toujours d'une fin de ligne.
    for numero, ligne in enumerate(lignes):
        lignes[numero], repares = recoller_dans_la_ligne(ligne, entiers, composes)
        recollees += repares

    # Redecoupage en pages, aux memes frontieres.
    pages_reparees, precedent = [], 0
    for frontiere in frontieres:
        pages_reparees.append("\n".join(lignes[precedent:frontiere]))
        precedent = frontiere
    return pages_reparees, recollees


# Caracteres qui n'apparaissent JAMAIS dans un texte de loi francais.
# Ils ne sortent que d'un trait manuscrit, d'un tampon ou d'un pli de
# reliure interprete comme un glyphe.
RE_IMPOSSIBLE = re.compile(r"[#=~^|{}\\]")

# Un mot d'au moins quatre lettres : la preuve qu'il y a du texte reel
# sur la ligne, et pas seulement des traits.
RE_MOT_REEL = re.compile(r"[A-Za-zÀ-ÿ]{4,}")


def retirer_lignes_parasites(pages: list[str]) -> tuple[list[str], int]:
    """Retire les lignes qui ne portent aucun texte, seulement des traits.

    LE CAS REEL. Le Journal officiel de l'AUPSRVE est un exemplaire
    PARAPHE A LA MAIN : chaque page porte les initiales des ministres
    signataires. Meme apres avoir blanchi l'encre coloree, des residus
    de traits subsistent, que Tesseract rend en suites du genre
    « AD | p FAT # pa Te, A eu Ps 15 » — inserees au milieu des articles,
    a l'endroit des coupures de page.

    LA REGLE EST VOLONTAIREMENT PRUDENTE : une ligne n'est retiree que si
    elle contient un caractere impossible ET aucun mot d'au moins quatre
    lettres. Mesure sur ce document : 60 lignes retirees, toutes du
    charabia ; 19 lignes conservees bien qu'elles portent un symbole,
    toutes du vrai texte — dont « |) les decisions juridictionnelles »,
    ou la barre est un « 1 » mal lu.

    Autrement dit : en cas de doute, on garde. Un fragment parasite qui
    passe se voit a la relecture ; un alinea supprime, non.
    """
    retirees = 0
    nettoyees: list[str] = []

    for page in pages:
        gardees = []
        for ligne in page.splitlines():
            nue = ligne.strip()
            if nue and RE_IMPOSSIBLE.search(nue) and not RE_MOT_REEL.search(nue):
                retirees += 1
                continue
            gardees.append(ligne)
        nettoyees.append("\n".join(gardees))

    return nettoyees, retirees


def nettoyer_pages(brutes: list[str]) -> tuple[list[str], dict]:
    """En-tetes, pieds de page et cesures : le traitement commun.

    IL S'APPLIQUE AUSSI AU TEXTE ISSU D'UN OCR. Le passage par Tesseract
    ne fait pas disparaitre les defauts que ce module corrige — il les
    aggrave, puisque l'OCR lit AUSSI le titre courant et le folio
    imprimes sur chaque page. Le Journal officiel de l'AUPSRVE repete
    ainsi « ACTE UNIFORME PORTANT ORGANISATION DES PROCEDURES
    SIMPLIFIEES... » en tete de ses 115 pages : sans ce nettoyage, cette
    ligne se retrouve collee dans le contenu d'un article sur deux, et
    part telle quelle a la vectorisation.

    C'est la raison d'etre de cette fonction : les deux chemins
    d'extraction, natif et OCR, doivent la traverser.
    """
    # Les en-tetes AVANT les cesures : un pied de page intercale entre
    # "unifor-" et "me" empeche de reconnaitre la coupure. Les retirer
    # d'abord remet les deux morceaux cote a cote.
    repetees = reperer_repetitions(brutes)
    nettoyees = [retirer_repetitions(texte, repetees) for texte in brutes]
    nettoyees, recollees = recoller_cesures(nettoyees)

    diagnostic = {
        "lignes_repetees_retirees": sorted(repetees)[:10],
        "cesures_recollees": recollees,
    }
    return nettoyees, diagnostic


def extraire(contenu: bytes) -> tuple[list[tuple[int, str]], dict]:
    """Extrait le texte page par page, avec un diagnostic de mise en page.

    Le diagnostic remonte jusqu'a l'administrateur : savoir qu'un
    document etait sur deux colonnes, ou qu'on lui a retire des
    en-tetes, change la facon dont il relit le decoupage.
    """
    with pdfplumber.open(io.BytesIO(contenu)) as pdf:
        brutes: list[str] = []
        pages_deux_colonnes = 0
        for page in pdf.pages:
            texte, deux_colonnes = extraire_page(page)
            brutes.append(texte)
            pages_deux_colonnes += int(deux_colonnes)

    nettoyees, diagnostic = nettoyer_pages(brutes)
    pages = list(enumerate(nettoyees, 1))

    diagnostic |= {
        "pages": len(pages),
        "pages_deux_colonnes": pages_deux_colonnes,
        "caracteres_par_page": (
            sum(len(t) for _, t in pages) / len(pages) if pages else 0
        ),
    }
    return pages, diagnostic


# ---------------------------------------------------------------------
# Aides a l'OCR
#
# Elles ne dependent pas de pdfplumber : elles travaillent sur une image
# deja rendue, quelle qu'en soit la provenance — page d'un PDF scanne,
# ou image publiee telle quelle par l'editeur officiel. C'est pourquoi
# elles vivent ici plutot que dans ingestion/1_extraire.py, dont le nom
# commence par un chiffre et qui n'est donc pas importable.
# ---------------------------------------------------------------------

EMPLACEMENTS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def localiser_tesseract() -> str | None:
    """Chemin du binaire Tesseract, PATH d'abord puis emplacements usuels."""
    import os
    import shutil
    from pathlib import Path

    trouve = shutil.which("tesseract")
    if trouve:
        return trouve
    force = os.environ.get("TESSERACT_CMD")
    if force and Path(force).exists():
        return force
    for candidat in EMPLACEMENTS_TESSERACT:
        if Path(candidat).exists():
            return candidat
    return None


# Part de pixels sombres en dessous de laquelle une page est tenue pour
# blanche. Une page de texte en compte plusieurs pour cent ; une page
# vide, quasiment aucun.
PART_PAGE_BLANCHE = 0.002


def page_blanche(image) -> bool:
    """La page ne porte-t-elle rien ?

    POURQUOI CE TEST EXISTE. Le Code general des impots tel que publie
    par la DGI est une impression du site web : 2042 pages, dont environ
    1770 BLANCHES — les sauts de page du navigateur. Les OCRiser coutait
    une demi-heure de calcul pour produire des pages vides, et surtout
    noyait le vrai contenu dans le fichier de sortie.

    Le test porte sur l'image DEJA RENDUE : le rendu est la partie bon
    marche, l'OCR la partie chere. On ne rend jamais deux fois.
    """
    gris = image.convert("L")
    histogramme = gris.histogram()
    sombres = sum(histogramme[:200])
    return sombres / (gris.width * gris.height) < PART_PAGE_BLANCHE
