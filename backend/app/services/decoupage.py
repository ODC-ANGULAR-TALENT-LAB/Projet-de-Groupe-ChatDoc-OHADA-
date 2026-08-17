"""Decoupage d'un texte officiel en articles.

C'est l'etape centrale de tout le projet : c'est elle qui rend les
citations exactes possibles. On parcourt le texte ligne a ligne en
maintenant un "etat" de la hierarchie courante (livre, titre, chapitre,
section), et des qu'on rencontre un en-tete d'article, on clot l'article
precedent et on en ouvre un nouveau.

CE MODULE EST LA SEULE IMPLEMENTATION DU DECOUPAGE. Les scripts
d'ingestion en ligne de commande et le back-office d'administration
l'importent tous les deux. Un corpus mal decoupe contamine tout ce qui
vient apres ; deux implementations qui divergent seraient le pire des
defauts possibles.
"""

from __future__ import annotations

import re

# Marqueur de page pose par l'extraction.
RE_PAGE = re.compile(r"^===PAGE (\d+)===\s*$")

# Forme d'un numero d'article. Plusieurs ecritures coexistent :
#   "92"          numero simple
#   "18 bis"      article insere, notation latine
#   "50-1"        article insere, notation numerique
#   "626-1-1-1"   insertion dans une insertion — l'AUSCGIE revise en
#                 2014 descend jusqu'a QUATRE niveaux
#
# La profondeur n'est volontairement pas bornee. Capturer un niveau de
# moins fait fusionner des articles distincts : avec deux niveaux
# seulement, Art.626-1, 626-1-1, 626-1-1-1, 626-1-2, 626-1-2-1 et
# 626-1-3 se confondent en un seul "626-1". Ce sont les articles ajoutes
# par la revision — sa raison d'etre — et une citation renverrait alors
# au mauvais texte.
# Prefixe de livre. Le Code general des impots numerote ses trois livres
# dans des series distinctes, et son article premier le dit lui-meme :
#
#   « le livre premier traite de differents types d'impots (Articles 2 a
#     613), le livre deuxieme regit les procedures fiscales (Articles L1
#     a L146), le livre troisieme traite de la fiscalite locale
#     (Articles C1 a C149) »
#
# Sans ce prefixe, les articles L et C ne sont pas reconnus du tout :
# leur texte est absorbe par l'article precedent, silencieusement. Cela
# represente pres de 320 articles pour ce seul code.
#
# LA LETTRE EST CONSERVEE DANS LE NUMERO. « L 6 », « C 6 » et « 6 » sont
# trois articles differents du meme code ; les confondre ferait citer le
# mauvais texte. C'est aussi la forme sous laquelle le code se cite.
#
# R et D sont admis pour les parties reglementaire et decretale, qui
# suivent la meme convention dans les codes francais.
# LE SOULIGNE EST TOLERE APRES LA LETTRE. L'OCR rend regulierement
# l'espace par un souligne : « Article C _54 » au lieu de « Article
# C 54 ». Sans cette tolerance l'en-tete n'est pas reconnu du tout, et
# l'article se retrouve absorbe dans le precedent — c'est ainsi que
# l'article C 54, celui qui fixe le taux des centimes additionnels
# communaux, avait disparu au milieu du contenu de C 53.
PREFIXE_CODE = r"(?:[LRDC][\s_]*)?"

# Ordinaux latins d'insertion. LA SERIE VA BIEN AU-DELA DE « quinquies ».
# Le Code general des impots monte jusqu'a « undecies » et compose meme
# « 93 nonies bis ». Le motif s'arretait a quinquies : « Article 18
# sexies » etait alors lu comme un SECOND « Article 18 », dont le
# contenu commencait par « sexies.- ». Mesure sur le CGI : 11 numeros
# en double, dont un article 93 apparaissant huit fois.
#
# Un numero en double n'est pas un defaut cosmetique : il rend toute
# citation ambigue — « CGI article 93 » ne designe plus rien de precis.
ORDINAL_LATIN = (
    r"(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies"
    r"|decies|undecies|duodecies|terdecies|quaterdecies|quindecies)"
)

# Les ordinaux se cumulent : « nonies bis » suit « nonies ».
#
# LE SOULIGNE EST TOLERE ENTRE LE NUMERO ET L'ORDINAL. L'OCR du Code
# general des impots rend regulierement l'espace par un souligne :
# « Article 558 _bis », « Article 93 _ quinquies », « Article L 33
# __bis ». Sans cette tolerance, l'ordinal n'est pas capture et
# l'article devient un DOUBLON de son voisin — « 558 » deux fois, dont
# l'un commence par « _bis.- ».
#
# Le souligne n'apparait jamais dans un numero d'article legitime : le
# tolerer ici ne cree donc aucune confusion possible.
# DEUX BRUITS D'OCR TOLERES ENTRE LE NUMERO ET L'ORDINAL :
#
#   - le POINT, « Article L 6. Ter » au lieu de « L 6 ter » ;
#   - une LETTRE PARASITE collee a l'ordinal, « Article 93 mnonies ».
#
# La tolerance est sans danger parce que la liste des ordinaux est
# CLOSE : la lettre optionnelle ne peut etre absorbee que si ce qui
# suit forme exactement l'un de ces mots, qui n'existent pas ailleurs
# en francais courant. Verifie sans regression sur les onze actes
# uniformes deja charges.
#
# Sans elles, l'ordinal n'est pas capture et l'article devient un
# DOUBLON de son voisin : « Article 93 » se retrouvait porte par deux
# articles distincts, ce qui rend la citation « CGI article 93 »
# ambigue — exactement ce que ce produit existe pour eviter.
SUFFIXE = rf"(?:[\s_.]*[a-z]?{ORDINAL_LATIN})*"

# Suffixe litteral : le CGI ecrit « Article 124 A », « Article 93 bis A ».
#
# LE SEPARATEUR DOIT SUIVRE IMMEDIATEMENT. Sans cette exigence, « Article
# 92 A compter du 1er janvier » — une phrase, pas un en-tete — serait lu
# comme l'article « 92 A ». La lettre n'est donc acceptee que collee a
# son point ou son tiret.
SUFFIXE_LETTRE = r"(?:\s*[A-Z](?=[.\-–:]))?"

NUMERO = rf"{PREFIXE_CODE}\d+(?:\s*-\s*\d+)*{SUFFIXE}{SUFFIXE_LETTRE}"

# En-tete d'article. Deux ecritures selon l'edition :
#   "Article 92", "Article 18 bis", "ARTICLE 5 :"
#   "Art.92.-", "Art.50-1.-"
# La forme abregee exige un separateur apres le numero : sans lui,
# "Art. 5 du present acte" au fil d'une phrase serait pris pour un
# debut d'article.
# Guillemets et apostrophes pouvant preceder le titre. Un acte qui en
# modifie un autre cite le texte remplace entre guillemets, et le
# guillemet fermant se retrouve colle au titre suivant : l'AUPC 2015
# ecrit "»Article 191". Sans cette tolerance, l'article n'est pas
# reconnu et son contenu est absorbe par le precedent.
GUILLEMETS = r"[«»\"'“”‘’\s]*"

RE_ARTICLE = re.compile(
    rf"^{GUILLEMETS}(?:"
    rf"Article\s+(?P<long>{NUMERO})\s*[.\-–:]?"
    rf"|"
    # « Article premier » : ecriture courante du premier article d'un
    # code francais. Le separateur est EXIGE ici, alors qu'il est
    # facultatif apres un numero chiffre : « premier » est un mot
    # ordinaire, et « Article premier alinea 2 » au fil d'une phrase ne
    # doit pas ouvrir un article.
    rf"Article\s+(?P<premier>premi[eè]re?)\s*[.\-–:]"
    rf"|"
    rf"Art\.?\s*(?P<court>{NUMERO})\s*[.\-–]+"
    rf")",
    re.I,
)


def numero_article(correspondance: re.Match) -> str:
    """Numero capture, quelle que soit l'ecriture reconnue.

    "50 - 1" devient "50-1" : les espaces autour du tiret varient d'une
    edition a l'autre, le numero d'un article non.

    « Article premier » devient "1". LES DIX ACTES DEJA EN BASE
    NUMEROTENT TOUS LEUR PREMIER ARTICLE "1" : garder "premier" ferait
    du meme article deux choses selon le texte, et une recherche sur
    « article 1 du CGI » ne le retrouverait pas.
    """
    if correspondance.group("premier"):
        return "1"
    brut = correspondance.group("long") or correspondance.group("court")

    # LE BRUIT D'OCR NE DOIT PAS ENTRER DANS LE NUMERO. On le tolere
    # pour RECONNAITRE l'en-tete, mais le garder donnerait des articles
    # numerotes « 558 _bis », « L 6. ter » ou « 93 mnonies » — qu'aucune
    # citation « article 558 bis » ne retrouverait jamais.
    #
    # Chaque ordinal est donc reecrit proprement : une espace devant,
    # en minuscules. Les editions ecrivent « Ter » ou « ter » selon les
    # articles, et « L 6 Ter » ne doit pas devenir un article distinct
    # de « L 6 ter ».
    propre = re.sub(
        rf"[\s_.]*[a-z]?({ORDINAL_LATIN})",
        lambda mot: " " + mot.group(1).lower(),
        brut,
        flags=re.I,
    )

    propre = re.sub(r"\s*-\s*", "-", " ".join(propre.split()))

    # LE PREFIXE DE LIVRE PORTE TOUJOURS UNE ESPACE. L'edition ecrit
    # tantot « Article C 46 », tantot « Article C46 » : sans cette
    # normalisation, le corpus contiendrait les deux formes, et une
    # citation « article C 46 » ne retrouverait pas « C46 ».
    return re.sub(r"^([LRDC])[\s_]*(\d)", r"\1 \2", propre)

# Certains niveaux ne portent pas de numero mais un ordinal ecrit :
# l'AUPC comme l'AUS s'ouvrent sur un "TITRE PRELIMINAIRE". Non
# reconnu, ce titre laisse sans chemin hierarchique tous les articles
# qui en dependent — huit dans l'AUPC, a commencer par l'article 1er,
# celui qui definit l'objet meme de l'acte.
#
# LA LISTE EST CLOSE A DESSEIN. Accepter un mot quelconque a la place
# du numero ferait prendre pour un en-tete toute phrase commencant par
# "Partie", "Titre" ou "Livre" — et le corpus en compte des dizaines :
# "Partie aupres duquel elle est immatriculee." deviendrait un niveau,
# et tous les articles suivants en heriteraient.
ORDINAL_ECRIT = r"(?:pr[ée]liminaire|premi[eè]re?|unique)"

# La barre verticale est un I mal lu. Tesseract rend regulierement
# "LIVRE I" en "LIVRE |" : les deux formes se ressemblent trait pour
# trait dans une police a empattements. Mesure sur le Journal officiel
# de l'AUPSRVE : vingt en-tetes de niveau perdus pour ce seul caractere,
# dont des LIVRE et des CHAPITRE — leurs articles heritaient alors du
# niveau precedent, donc d'un chemin FAUX.
#
# La tolerance est sans risque : la barre verticale n'apparait jamais
# dans un texte de loi francais, et elle n'est acceptee qu'ICI, a la
# place d'un numero de niveau. L'expression des articles ne la connait
# pas.
ROMAIN = r"[IVXLC|]"

# Numero d'un niveau. Comme pour les articles, la numerotation peut
# etre composee : l'AUSCGIE revise ajoute un "Livre 4-2" consacre a la
# societe par actions simplifiee. Sans le second segment, ce livre
# porterait le meme numero que le Livre 4 et les articles des deux
# heriteraient d'un chemin identique.
# UN CHIFFRE ROMAIN NE PEUT PAS ETRE SUIVI D'UNE LETTRE.
#
# Sans cette frontiere, et parce que la reconnaissance est insensible a
# la casse (il faut bien accepter « LIVRE » comme « Livre »), le « l »
# de « la » passe pour un romain :
#
#   « ... a la partie la plus diligente. »
#        -> niveau « Partie L », intitule « a plus diligente. »
#   « PARTIE LEGISLATIVE »
#        -> niveau « Partie L », intitule « EGISLATIVE »
#
# Mesure sur le corpus deja charge : 311 articles (29 de l'AUA, 282 de
# l'AUPC) classes sous une hierarchie inventee. Ce n'est pas cosmetique
# — le chemin est montre a l'utilisateur ET sert de prefixe a la
# vectorisation, donc un chemin faux deplace l'article dans l'espace
# semantique.
FIN_DE_NUMERO = r"(?![A-Za-zÀ-ÿ])"

NUMERO_NIVEAU = (
    rf"(?:{ORDINAL_ECRIT}|{ROMAIN}+{FIN_DE_NUMERO}|\d+(?:\s*-\s*\d+)*)"
)


def _regex_niveau(mot: str) -> re.Pattern:
    return re.compile(
        rf"^\s*{mot}\s+({NUMERO_NIVEAU})\s*[:.\-]?\s*(.*)$", re.I
    )


# Niveaux de la hierarchie, du plus large au plus fin.
# "Partie" chapeaute le livre dans l'AUSCGIE : l'omettre laisserait les
# articles de la partie suivante heriter du dernier livre de la
# precedente.
RE_NIVEAUX = [
    ("partie", _regex_niveau("PARTIE")),
    ("livre", _regex_niveau("LIVRE")),
    ("titre", _regex_niveau("TITRE")),
    ("chapitre", _regex_niveau("CHAPITRE")),
    ("section", _regex_niveau("SECTION")),
]
ORDRE = ["partie", "livre", "titre", "chapitre", "section"]

# Espaces exotiques produits par l'extraction PDF. Laisses tels quels,
# ils cassent les comparaisons de numeros : "18 bis" avec un espace
# insecable et "18 bis" avec un espace ordinaire deviennent deux
# articles differents.
ESPACES_EXOTIQUES = (
    " ",  # espace insecable
    " ",  # espace insecable etroit
    " ",  # espace fine
    "﻿",  # marque d'ordre des octets egaree
    "​",  # espace sans chasse
)


# Tirets typographiques. Les editions juridiques utilisent souvent le
# trait d'union U+2010 la ou le clavier tape U+002D. Sans normalisation,
# "Art.7.‐" et "Titre 2 ‐ Qualite d'associe" ne sont reconnus ni comme
# article ni comme niveau : le decoupage rate en silence.
TIRETS_EXOTIQUES = (
    "‐",  # U+2010 trait d'union
    "‑",  # U+2011 trait d'union insecable
    "‒",  # U+2012 tiret numerique
    "–",  # U+2013 tiret demi-cadratin
    "—",  # U+2014 tiret cadratin
    "−",  # U+2212 signe moins
)


# Ligne de sommaire : un intitule, des points de conduite, un numero de
# page. Le sommaire reprend mot pour mot les en-tetes de la hierarchie,
# et il precede le corps du texte : sans ce filtre, le DERNIER titre du
# sommaire reste en memoire et le premier article du document herite du
# dernier livre de l'ouvrage. C'est exactement ce qui s'est produit sur
# l'AUDCG, ou l'article 1 se retrouvait classe en "Livre 9 - Dispositions
# transitoires et finales".
#
# La plage de pages (page_debut) protege deja les documents dont on
# connait la pagination. Ce filtre couvre les autres, notamment le
# back-office ou l'administrateur depose un PDF sans indiquer ou commence
# le corps du texte. Aucun texte de loi n'emploie de points de conduite.
RE_SOMMAIRE = re.compile(r"\.{4,}\s*\d*\s*$")


# Zone privee Unicode. Les polices Symbol et Wingdings y logent leurs
# glyphes : une puce de liste composee en Symbol sort de l'extraction en
# U+F0B7, et l'espace qui la suit en U+F020.
#
# CES CARACTERES SONT INVISIBLES OU ILLISIBLES PARTOUT AILLEURS. Stockes
# tels quels, ils partent dans le contenu de l'article — donc dans
# l'extrait montre a l'utilisateur comme texte officiel, et dans le
# texte vectorise. Mesure sur ce corpus : 803 occurrences dans 190
# articles de l'AUSCGIE, de l'AUDCG et de l'AUS.
#
# La correspondance n'est pas arbitraire : une police symbolique place
# ses glyphes a U+F000 + le code ASCII de la touche. U+F020 correspond
# donc a l'espace, et U+F0B7 au caractere 0xB7, la puce.
DEBUT_ZONE_PRIVEE = 0xE000
FIN_ZONE_PRIVEE = 0xF8FF
SYMBOLES_CONNUS = {
    "": " ",   # espace
    "": "•",   # puce de liste
    "": "•",   # puce carree
    "": "-",   # trait d'union
}


def _hors_zone_privee(caractere: str) -> str:
    """Equivalent lisible d'un glyphe de police symbolique.

    Un caractere inconnu de la zone privee devient une espace : on ne
    devine pas un glyphe qu'on ne connait pas, et une espace ne peut pas
    faire dire au texte autre chose que ce qu'il dit.
    """
    if caractere in SYMBOLES_CONNUS:
        return SYMBOLES_CONNUS[caractere]
    return " "


def normaliser(ligne: str) -> str:
    """Ramene espaces, tirets et glyphes exotiques a des equivalents lisibles."""
    for exotique in ESPACES_EXOTIQUES:
        ligne = ligne.replace(exotique, " ")
    for exotique in TIRETS_EXOTIQUES:
        ligne = ligne.replace(exotique, "-")

    if any(DEBUT_ZONE_PRIVEE <= ord(c) <= FIN_ZONE_PRIVEE for c in ligne):
        ligne = "".join(
            _hors_zone_privee(c)
            if DEBUT_ZONE_PRIVEE <= ord(c) <= FIN_ZONE_PRIVEE
            else c
            for c in ligne
        )
    return ligne


def etiquette_niveau(nom: str, numero: str, intitule: str) -> str:
    """Construit un maillon du chemin hierarchique.

    L'intitule est conserve quand il est present : "Titre II - Des
    assemblees generales" porte beaucoup plus de sens que "Titre II",
    et ce chemin sert de prefixe a la vectorisation.

    Le numero est mis en capitales, car c'est presque toujours un
    chiffre romain que l'extraction peut rendre en minuscules ("titre
    ii"). Un ordinal ecrit, lui, se compose comme un mot : le chemin
    sert de prefixe a la vectorisation, et "Titre PRELIMINAIRE" y
    entrerait comme une anomalie typographique.
    """
    if re.fullmatch(ORDINAL_ECRIT, numero, re.I):
        numero = numero.capitalize()
    else:
        # La barre verticale acceptee ci-dessus est retablie en I : le
        # chemin affiche a l'utilisateur, et le prefixe de vectorisation,
        # doivent porter "Livre I" et non "Livre |".
        numero = numero.upper().replace("|", "I")
    etiquette = f"{nom.capitalize()} {numero}"
    intitule = " ".join(intitule.split())
    if intitule:
        etiquette += f" - {intitule}"
    return etiquette


def decouper_lignes(
    lignes, page_debut: int = 1, page_fin: int | None = None
) -> list[dict]:
    """Decoupe un flux de lignes en articles.

    Accepte n'importe quel iterable de chaines : un fichier ouvert
    (ligne de commande) comme un texte en memoire (back-office).
    """
    contexte: dict[str, str] = {}
    articles: list[dict] = []
    courant: dict | None = None
    page_courante = 0

    for ligne in lignes:
        brut = normaliser(ligne.rstrip())

        # 0) changement de page ?
        marqueur = RE_PAGE.match(brut)
        if marqueur:
            page_courante = int(marqueur.group(1))
            continue

        # Les pages hors de la plage demandee sont ignorees : c'est ainsi
        # qu'on ecarte le sommaire, qui produirait sinon autant de faux
        # articles.
        if page_courante < page_debut:
            continue
        if page_fin is not None and page_courante > page_fin:
            continue

        # 0 bis) une ligne de sommaire ? elle ressemble a un en-tete de
        # niveau mais n'en est pas un. Voir RE_SOMMAIRE.
        if RE_SOMMAIRE.search(brut):
            continue

        # 1) un en-tete de niveau ? on reinitialise les niveaux inferieurs
        entete = False
        for nom, regex in RE_NIVEAUX:
            trouve = regex.match(brut)
            if trouve:
                contexte[nom] = etiquette_niveau(
                    nom, trouve.group(1), trouve.group(2) or ""
                )
                for inferieur in ORDRE[ORDRE.index(nom) + 1 :]:
                    contexte.pop(inferieur, None)
                entete = True
                break
        if entete:
            continue

        # 2) un debut d'article ? on clot le precedent
        trouve = RE_ARTICLE.match(brut)
        if trouve:
            if courant:
                articles.append(courant)
            courant = {
                "numero": numero_article(trouve),
                "chemin": " > ".join(
                    contexte[niveau] for niveau in ORDRE if niveau in contexte
                ),
                "contenu": brut[trouve.end() :].strip(),
                "page_debut": page_courante,
            }

        # 3) sinon, la ligne prolonge l'article en cours
        elif courant and brut.strip():
            courant["contenu"] += " " + brut.strip()

    if courant:
        articles.append(courant)

    # Les lignes ont ete recollees avec des espaces simples ; on nettoie
    # les doublons introduits par les fins de ligne.
    for article in articles:
        article["contenu"] = " ".join(article["contenu"].split())

    return articles


def decouper_texte(
    texte: str, page_debut: int = 1, page_fin: int | None = None
) -> list[dict]:
    """Decoupe un texte pagine deja charge en memoire."""
    return decouper_lignes(texte.splitlines(), page_debut, page_fin)
