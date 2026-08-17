"""Tests du decoupage en articles (B.3).

Le decoupage est l'etape la plus determinante du projet : un corpus mal
decoupe contamine tout ce qui vient apres, et le bug se decouvre trois
semaines plus tard, dans l'interface, ou il est incomprehensible.

Ces tests figent le comportement attendu. Ils sont a rejouer a chaque
retouche des expressions regulieres - et il y en aura, chaque texte
officiel ayant ses habitudes typographiques.
"""

from __future__ import annotations

import pytest

# Espace insecable, ecrit en echappement pour rester visible a la
# relecture : c'est precisement le caractere que le decoupage doit
# neutraliser.
INSECABLE = " "

# Texte fabrique reproduisant les pieges reels d'un PDF officiel :
# un sommaire en page 1, des intitules de niveaux, un numero avec
# espace insecable, un article sur plusieurs lignes, et un changement
# de titre qui doit reinitialiser les niveaux inferieurs.
TEXTE_ESSAI = (
    "\n===PAGE 1===\n"
    "SOMMAIRE\n"
    "Article 1 .......... 3\n"
    "Article 2 .......... 3\n"
    "\n===PAGE 2===\n"
    "LIVRE I : DISPOSITIONS GENERALES\n"
    "TITRE II - Des assemblees generales\n"
    "CHAPITRE 3\n"
    "Article 1 : La presente loi regit les societes commerciales\n"
    "et le groupement d'interet economique.\n"
    f"Article 18{INSECABLE}bis\n"
    "Cet article porte un numero avec espace insecable.\n"
    "\n===PAGE 3===\n"
    "SECTION 2 : Du capital social\n"
    "Article 19 - Le capital social est divise en parts sociales.\n"
    "Chaque part represente une fraction du capital.\n"
    "TITRE III : Des sanctions\n"
    "Article 20. Toute infraction est punie.\n"
)


@pytest.fixture
def fichier_essai(tmp_path):
    chemin = tmp_path / "essai.txt"
    chemin.write_text(TEXTE_ESSAI, encoding="utf-8")
    return chemin


@pytest.fixture
def articles(decoupeur, fichier_essai):
    """Decoupage du corps du texte, sommaire ecarte."""
    return decoupeur.decouper(fichier_essai, page_debut=2)


def par_numero(articles: list[dict], numero: str) -> dict:
    return next(article for article in articles if article["numero"] == numero)


def test_le_sommaire_est_neutralise_sans_filtre_de_page(decoupeur, fichier_essai):
    """Les points de conduite suffisent a reconnaitre un sommaire.

    L'option --page-debut suppose qu'on connaisse la pagination du
    document. Le back-office, lui, recoit un PDF sans cette indication :
    il faut donc que le sommaire soit ecarte sans elle. Sinon il
    fabrique des articles en double, et surtout il laisse en memoire le
    DERNIER titre de la table des matieres, dont herite alors le premier
    article du corps du texte.
    """
    tous = decoupeur.decouper(fichier_essai)
    numeros = [article["numero"] for article in tous]

    assert numeros.count("1") == 1
    assert numeros == ["1", "18 bis", "19", "20"]


def test_le_sommaire_ne_pollue_pas_le_chemin_hierarchique(decoupeur, fichier_essai):
    """Le defaut le plus sournois : pas un article en trop, un chemin faux.

    Constate sur l'AUDCG, dont l'article 1 se retrouvait classe sous le
    dernier livre de l'ouvrage, lu dans la table des matieres.
    """
    premier = decoupeur.decouper(fichier_essai)[0]

    assert "..." not in premier["chemin"]
    assert premier["chemin"].startswith("Livre I")


def test_page_debut_ecarte_le_sommaire(articles):
    assert [article["numero"] for article in articles] == [
        "1",
        "18 bis",
        "19",
        "20",
    ]


def test_espace_insecable_normalise(articles):
    """Le meme numero ecrit avec un espace insecable ou un espace
    ordinaire doit donner un seul et meme article."""
    numero = par_numero(articles, "18 bis")["numero"]
    assert numero == "18 bis"
    assert INSECABLE not in numero


def test_intitule_conserve_dans_le_chemin(articles):
    """Le chemin sert de prefixe a la vectorisation (B.7) : l'intitule
    des niveaux y porte l'essentiel du sens."""
    chemin = par_numero(articles, "1")["chemin"]
    assert chemin == (
        "Livre I - DISPOSITIONS GENERALES"
        " > Titre II - Des assemblees generales"
        " > Chapitre 3"
    )


def test_niveaux_inferieurs_reinitialises(articles):
    """Un nouveau titre doit effacer le chapitre et la section
    precedents, sinon les articles heritent d'un contexte faux."""
    chemin = par_numero(articles, "20")["chemin"]
    assert chemin == "Livre I - DISPOSITIONS GENERALES > Titre III - Des sanctions"
    assert "Chapitre" not in chemin
    assert "Section" not in chemin


def test_section_ajoutee_sans_effacer_le_chapitre(articles):
    chemin = par_numero(articles, "19")["chemin"]
    assert chemin.endswith("Chapitre 3 > Section 2 - Du capital social")


def test_contenu_multiligne_recolle(articles):
    assert par_numero(articles, "1")["contenu"] == (
        "La presente loi regit les societes commerciales "
        "et le groupement d'interet economique."
    )


def test_aucun_marqueur_de_page_dans_le_contenu(articles):
    assert all("===PAGE" not in article["contenu"] for article in articles)


def test_page_de_depart_tracee(articles):
    """La page permet de retrouver l'article dans le PDF pendant la
    relecture humaine (B.5)."""
    assert par_numero(articles, "1")["page_debut"] == 2
    assert par_numero(articles, "20")["page_debut"] == 3


def test_page_fin_borne_le_decoupage(decoupeur, fichier_essai):
    articles = decoupeur.decouper(fichier_essai, page_debut=2, page_fin=2)
    assert [article["numero"] for article in articles] == ["1", "18 bis"]


def test_texte_sans_article_ne_produit_rien(decoupeur, tmp_path):
    chemin = tmp_path / "vide.txt"
    chemin.write_text("\n===PAGE 1===\nUn texte sans en-tete d'article.\n", "utf-8")
    assert decoupeur.decouper(chemin) == []


def test_titre_preliminaire_reconnu_comme_niveau(decoupeur, tmp_path):
    """Un niveau peut porter un ordinal ecrit au lieu d'un numero.

    L'AUPC comme l'AUS s'ouvrent sur un "TITRE PRELIMINAIRE". Tant
    qu'il n'etait pas reconnu, les huit premiers articles de l'AUPC —
    dont l'article 1er, celui qui definit l'objet de l'acte — arrivaient
    en base sans aucun chemin hierarchique.
    """
    chemin = tmp_path / "preliminaire.txt"
    chemin.write_text(
        "\n===PAGE 1===\n"
        "TITRE PRELIMINAIRE - DISPOSITIONS GENERALES\n"
        "Article 1\n"
        "Le present Acte uniforme a pour objet :\n"
        "TITRE I - Du reglement preventif\n"
        "Article 2\n"
        "La procedure est ouverte au debiteur.\n",
        encoding="utf-8",
    )
    articles = decoupeur.decouper(chemin)

    assert par_numero(articles, "1")["chemin"] == (
        "Titre Preliminaire - DISPOSITIONS GENERALES"
    )
    # Le titre numerote qui suit remplace le preliminaire, il ne s'y
    # ajoute pas.
    assert par_numero(articles, "2")["chemin"] == "Titre I - Du reglement preventif"


def test_une_phrase_commencant_par_un_mot_de_niveau_n_est_pas_un_en_tete(
    decoupeur, tmp_path
):
    """Le garde-fou de la regle precedente.

    Accepter un mot quelconque a la place du numero de niveau ferait
    reconnaitre comme en-tete les dizaines de phrases du corpus qui
    commencent par "Partie", "Titre" ou "Livre" — et tous les articles
    suivants heriteraient d'un chemin fabrique de toutes pieces.
    """
    chemin = tmp_path / "phrases.txt"
    chemin.write_text(
        "\n===PAGE 1===\n"
        "LIVRE I - DES SURETES\n"
        "Article 1\n"
        "Partie aupres duquel elle est immatriculee.\n"
        "Titre doit preciser les modalites de determination.\n"
        "Article 2\n"
        "Le livre mentionne chronologiquement l'origine des ressources.\n",
        encoding="utf-8",
    )
    articles = decoupeur.decouper(chemin)

    assert [article["numero"] for article in articles] == ["1", "2"]
    assert all(
        article["chemin"] == "Livre I - DES SURETES" for article in articles
    )
    # Les phrases restent dans le contenu de leur article, elles n'ont
    # pas ete absorbees par la hierarchie.
    assert "immatriculee" in par_numero(articles, "1")["contenu"]


def test_tous_les_espaces_exotiques_sont_distincts(decoupeur):
    """Defaut latent du guide : une table dont les entrees se
    confondent ne neutralise rien du tout."""
    exotiques = decoupeur.ESPACES_EXOTIQUES
    assert len(set(exotiques)) == len(exotiques)
    assert all(caractere != " " for caractere in exotiques)


def test_barre_verticale_lue_comme_un_i_romain(decoupeur, tmp_path):
    """Tesseract rend « LIVRE I » en « LIVRE | » : les deux se ressemblent
    trait pour trait dans une police à empattements.

    Mesure sur le Journal officiel de l'AUPSRVE : vingt en-têtes de
    niveau perdus pour ce seul caractère. Leurs articles héritaient du
    niveau précédent — donc d'un chemin FAUX, ce qui est pire que pas de
    chemin du tout.
    """
    chemin = tmp_path / "ocr.txt"
    chemin.write_text(
        "\n===PAGE 1===\n"
        "LIVRE | LES PROCEDURES SIMPLIFIEES DE RECOUVREMENT\n"
        "CHAPITRE || DE LA REQUETE\n"
        "Article 1\n"
        "Le present acte regit les procedures.\n",
        encoding="utf-8",
    )

    article = decoupeur.decouper(chemin)[0]

    # La barre est rétablie en I dans le chemin affiché.
    assert article["chemin"] == (
        "Livre I - LES PROCEDURES SIMPLIFIEES DE RECOUVREMENT"
        " > Chapitre II - DE LA REQUETE"
    )
    assert "|" not in article["chemin"]


def test_la_barre_verticale_n_ouvre_pas_un_article(decoupeur, tmp_path):
    """La tolérance vaut pour les NIVEAUX seulement.

    L'expression des articles ne connaît pas la barre verticale : une
    ligne parasite d'OCR ne doit pas ouvrir un faux article.
    """
    chemin = tmp_path / "parasite.txt"
    chemin.write_text(
        "\n===PAGE 1===\n"
        "LIVRE | DES SURETES\n"
        "Article 1\n"
        "Un contenu.\n"
        "Article |\n"
        "Une ligne parasite issue de l'OCR.\n",
        encoding="utf-8",
    )

    numeros = [a["numero"] for a in decoupeur.decouper(chemin)]

    assert numeros == ["1"]


def test_les_glyphes_de_police_symbolique_sont_rendus_lisibles(decoupeur):
    """Défaut mesuré sur le corpus : 803 occurrences dans 190 articles.

    Une puce composée en police Symbol sort de l'extraction en U+F0B7,
    et l'espace qui la suit en U+F020 — des caractères de la zone privée
    Unicode, invisibles ou illisibles partout ailleurs. Stockés tels
    quels, ils partent dans l'extrait montré à l'utilisateur comme texte
    officiel, et dans le texte vectorisé.
    """
    ligne = "Les statuts mentionnent : \uf0b7\uf020 1° la forme de la société"

    normalisee = decoupeur.normaliser(ligne)

    assert "\uf0b7" not in normalisee
    assert "\uf020" not in normalisee
    assert "•" in normalisee
    assert "1° la forme de la société" in normalisee


def test_un_glyphe_prive_inconnu_devient_une_espace(decoupeur):
    """On ne devine pas un glyphe qu'on ne connaît pas.

    Une espace ne peut pas faire dire au texte autre chose que ce qu'il
    dit ; un caractère inventé, si.
    """
    normalisee = decoupeur.normaliser("le délai \uf0ff est de quinze jours")

    assert "\uf0ff" not in normalisee
    assert "le délai" in normalisee and "quinze jours" in normalisee


def test_la_normalisation_est_idempotente(decoupeur):
    """Renormaliser un texte déjà normalisé ne doit rien changer.

    C'EST CE QUI REND SÛRE LA CORRECTION EN PLACE DU CORPUS.
    ingestion/corriger_glyphes.py sélectionne les articles « que
    normaliser modifie » et réécrit leur contenu. Si la fonction n'était
    pas idempotente, chaque passage trouverait de nouveaux articles à
    corriger : le script réécrirait le corpus indéfiniment, en le
    dégradant un peu plus à chaque tour.

    C'est aussi ce qui garantit que corriger en place produit exactement
    ce qu'aurait produit un rechargement complet du texte.
    """
    original = (
        "Les statuts mentionnent :  1° la forme ; "
        " 2° le délai – de trente jours — suite  fin"
    )

    une_fois = decoupeur.normaliser(original)
    deux_fois = decoupeur.normaliser(une_fois)

    assert une_fois == deux_fois


# ---------------------------------------------------------------------
# Écritures propres au Code général des impôts
#
# Le CGI camerounais numérote la dernière de ses parties — le Livre des
# procédures fiscales — « Article L 1 », « Article L 6 ter », et ouvre
# le code par « Article premier ». Ni l'une ni l'autre de ces écritures
# n'était reconnue : leur texte était absorbé, sans bruit, par l'article
# précédent.
# ---------------------------------------------------------------------


def numero_reconnu(ligne: str) -> str | None:
    """Numéro que le découpage tire d'une ligne, ou None.

    On s'adresse au SERVICE, pas au script : app/services/decoupage.py
    est l'implémentation unique, partagée par la ligne de commande et
    par le back-office du juriste.
    """
    from app.services.decoupage import RE_ARTICLE, normaliser, numero_article

    trouve = RE_ARTICLE.match(normaliser(ligne))
    return numero_article(trouve) if trouve else None


@pytest.mark.parametrize(
    "ligne,attendu",
    [
        ("Article L 1.- Les impôts sont recouvrés...", "L 1"),
        ("Article L 6 ter.- Les états financiers...", "L 6 ter"),
        ("Art. L 21.- Le contrôle sur pièces...", "L 21"),
    ],
)
def test_un_article_du_livre_des_procedures_est_reconnu(ligne, attendu):
    """La lettre est CONSERVÉE dans le numéro.

    « L 6 » et « 6 » sont deux articles différents du même code. Les
    confondre ferait citer le mauvais texte — le défaut le plus grave
    possible pour ce produit, puisqu'il ne se voit qu'en relisant.
    """
    assert numero_reconnu(ligne) == attendu


@pytest.mark.parametrize(
    "ligne", ["Article premier.- Il est établi un impôt...", "Article premier :"]
)
def test_article_premier_est_ramene_au_numero_1(ligne):
    """Les dix actes déjà en base numérotent tous leur premier article « 1 ».

    Garder « premier » ferait du même article deux choses selon le
    texte, et une recherche sur « article 1 du CGI » ne le retrouverait
    pas.
    """
    assert numero_reconnu(ligne) == "1"


@pytest.mark.parametrize(
    "ligne",
    [
        # « premier » est un mot ordinaire : sans séparateur, la phrase
        # continue et il ne s'agit pas d'un en-tête.
        "Article premier alinéa 2 dispose que le contribuable...",
        # Un renvoi au fil du texte n'ouvre pas un article.
        "Lorsque l'article L 6 ter est applicable, le contribuable...",
        "Articles divers du présent code",
    ],
)
def test_ces_lignes_n_ouvrent_pas_un_article(ligne):
    """L'élargissement du motif ne doit pas fabriquer de faux articles.

    Un faux en-tête coupe un article en deux : la moitié basse perd sa
    référence, et la moitié haute est citée tronquée.
    """
    assert numero_reconnu(ligne) is None


# ---------------------------------------------------------------------
# Un chiffre romain ne peut pas être suivi d'une lettre
# ---------------------------------------------------------------------


def test_une_phrase_contenant_partie_la_n_ouvre_pas_un_niveau(decoupeur, tmp_path):
    """LE DÉFAUT QUE CE TEST EMPÊCHE DE REVENIR.

    La reconnaissance est insensible à la casse — il faut bien accepter
    « LIVRE » comme « Livre ». Sans frontière après le chiffre romain,
    le « l » de « la » passait donc pour un romain :

        « ... à la partie la plus diligente. »
             → niveau « Partie L », intitulé « a plus diligente. »

    Mesure sur le corpus : 311 articles (29 de l'AUA, 282 de l'AUPC)
    classés sous une hiérarchie inventée. Ce n'est pas cosmétique — le
    chemin est montré à l'utilisateur ET sert de préfixe à la
    vectorisation, donc un chemin faux déplace l'article dans l'espace
    sémantique.
    """
    chemin = tmp_path / "romain.txt"
    chemin.write_text(
        "\n===PAGE 1===\n"
        "LIVRE II - DE L'ARBITRAGE\n"
        "Article 1\n"
        "Le tribunal est saisi par la partie la plus diligente.\n"
        "Article 2\n"
        "La procédure se poursuit.\n",
        encoding="utf-8",
    )

    articles = decoupeur.decouper(chemin)

    # Les deux articles restent sous le livre réel.
    assert all(a["chemin"] == "Livre II - DE L'ARBITRAGE" for a in articles)
    assert all("Partie L" not in a["chemin"] for a in articles)


def test_partie_legislative_n_est_pas_lue_comme_partie_l(decoupeur, tmp_path):
    """Même défaut, autre déclencheur.

    « PARTIE LÉGISLATIVE » — l'en-tête du Livre des procédures fiscales
    du CGI — devenait niveau « Partie L », intitulé « ÉGISLATIVE ».
    """
    chemin = tmp_path / "legislative.txt"
    chemin.write_text(
        "\n===PAGE 1===\n"
        "LIVRE I - IMPÔTS\n"
        "PARTIE LEGISLATIVE\n"
        "Article 1\n"
        "Il est établi un impôt.\n",
        encoding="utf-8",
    )

    articles = decoupeur.decouper(chemin)

    assert "Partie L" not in articles[0]["chemin"]
    assert articles[0]["chemin"] == "Livre I - IMPÔTS"


def test_un_vrai_niveau_romain_reste_reconnu(decoupeur, tmp_path):
    """Le garde-fou de la règle précédente.

    La frontière ne doit pas coûter les en-têtes légitimes — c'est
    précisément ce qu'on cherchait à éviter en l'ajoutant.
    """
    chemin = tmp_path / "niveaux.txt"
    chemin.write_text(
        "\n===PAGE 1===\n"
        "LIVRE IV : DES SÛRETÉS\n"
        "TITRE XI - Du gage\n"
        "CHAPITRE III\n"
        "Article 1\n"
        "Le gage est un contrat.\n",
        encoding="utf-8",
    )

    articles = decoupeur.decouper(chemin)

    assert articles[0]["chemin"] == (
        "Livre IV - DES SÛRETÉS > Titre XI - Du gage > Chapitre III"
    )
