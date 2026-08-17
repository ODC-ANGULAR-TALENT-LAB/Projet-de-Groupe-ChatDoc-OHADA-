"""Tests de l'extraction et des écritures d'articles.

Chaque test ici correspond à un défaut trouvé sur un vrai PDF de texte
OHADA, pas à un cas imaginé. Ce sont des non-régressions.
"""

from __future__ import annotations

from app.services.decoupage import (
    RE_ARTICLE,
    decouper_texte,
    normaliser,
    numero_article,
)
from app.services.extraction import (
    nettoyer_pages,
    retirer_lignes_parasites,
    recoller_cesures,
    reperer_repetitions,
    retirer_repetitions,
)


# ---------------------------------------------------------------------
# Écritures des numéros d'articles
# ---------------------------------------------------------------------


def numero(ligne: str) -> str | None:
    trouve = RE_ARTICLE.match(normaliser(ligne))
    return numero_article(trouve) if trouve else None


def test_ecriture_longue():
    assert numero("Article 92") == "92"
    assert numero("ARTICLE 5 :") == "5"


def test_ecriture_abregee():
    """Forme employée par les éditions OHADA : « Art.92.- »."""
    assert numero("Art.92.- Le capital social...") == "92"
    assert numero("Art. 18. - Les associés...") == "18"


def test_tiret_typographique_reconnu():
    """Les éditions composent « Art.7.‐ » avec U+2010, pas le tiret-moins
    du clavier. Sans normalisation, l'article n'est pas reconnu."""
    assert numero("Art.7.‐ Une personne physique...") == "7"


def test_article_insere_notation_latine():
    assert numero("Article 18 bis") == "18 bis"


def test_article_insere_notation_numerique():
    """La révision 2014 de l'AUSCGIE numérote ainsi ses articles ajoutés.

    Perdre le suffixe ferait fusionner 50, 50-1, 50-2, 50-3 et 50-4 en
    un seul article — les articles nouveaux de la révision
    disparaîtraient dans leur article de base.
    """
    assert numero("Art.50-1.- Les apports en industrie...") == "50-1"
    assert numero("Art.50‐4.‐ Les titres sociaux...") == "50-4"


def test_espaces_autour_du_tiret_normalises():
    assert numero("Art. 50 - 1. - Les apports...") == "50-1"


def test_titre_precede_d_un_guillemet_fermant():
    """Défaut mesuré sur l'AUPC 2015 : « »Article 191 ».

    Un acte qui en modifie un autre cite le texte remplacé entre
    guillemets ; le guillemet fermant se colle au titre suivant. Sans
    tolérance, l'article n'est pas reconnu et son contenu vient grossir
    le précédent — une citation renverrait alors au mauvais texte.
    """
    assert numero("»Article 191") == "191"
    assert numero("« Art.50-1.- Les apports...") == "50-1"


def test_reference_en_cours_de_phrase_ignoree():
    """« Art. 5 du présent acte » en début de ligne ne doit pas ouvrir un
    article : la forme abrégée exige un séparateur après le numéro."""
    assert numero("Art. 5 du present acte uniforme dispose que") is None


def test_les_articles_inseres_restent_distincts():
    texte = (
        "\n===PAGE 1===\n"
        "Livre 1 - Constitution\n"
        "Art.50.- Les statuts contiennent l'evaluation des apports en nature.\n"
        "Art.50-1.- Les apports en industrie sont realises par la mise a "
        "disposition effective de la societe.\n"
        "Art.50-2.- L'apporteur en industrie doit rendre a la societe la "
        "contribution promise.\n"
    )

    numeros = [a["numero"] for a in decouper_texte(texte)]

    assert numeros == ["50", "50-1", "50-2"]


# ---------------------------------------------------------------------
# En-têtes et pieds de page
# ---------------------------------------------------------------------


def test_entete_repete_repere():
    """Une ligne présente sur toutes les pages est un en-tête, pas du
    contenu : sans retrait, elle est absorbée dans l'article qui
    chevauche la coupure de page."""
    pages = [f"www.editeur.com OHADA\nArticle {n}\nDu contenu." for n in range(1, 9)]

    assert "www.editeur.com OHADA" in reperer_repetitions(pages)


def page_realiste(numero: int, milieu: list[str], pied: str = "") -> str:
    """Page de texte de densité réaliste.

    Les pages à deux ou trois lignes ne testent rien : la détection des
    en-têtes repose sur la position, et sur une page si courte tout est
    un bord.
    """
    def remplissage(prefixe: str) -> list[str]:
        return [f"Phrase {prefixe} numero {i} sans importance particuliere." for i in range(4)]

    return "\n".join(
        [
            f"Titre courant de l'acte {numero}",
            *remplissage("avant"),
            *milieu,
            *remplissage("apres"),
            pied or f"— {numero} —",
        ]
    )


def test_ligne_de_contenu_non_reperee():
    pages = [
        page_realiste(n, [f"Un contenu different a chaque page {n}."])
        for n in range(1, 9)
    ]

    repetees = reperer_repetitions(pages)

    assert not any("contenu different" in ligne for ligne in repetees)


def test_pied_de_page_reduit_a_une_url():
    """Défaut mesuré sur l'AUPC : « http://…passif.html page 2 / 122 ».

    143 caractères, mais trois « mots » seulement — l'URL entière n'en
    compte qu'un. Un seuil exprimé en mots protège « Article 1 » et
    laisse passer ce pied de page, qui s'était alors inséré dans 121 des
    371 articles. Le critère doit porter sur la longueur.
    """
    url = "http://www.exemple.com/actes-uniformes/1668/acte-uniforme-procedures.html"
    pages = [
        page_realiste(n, ["Du contenu propre a la page."], pied=f"{url} page {n} / 12")
        for n in range(1, 13)
    ]

    conserve = retirer_repetitions(pages[0], reperer_repetitions(pages))

    assert "http" not in conserve


def test_pied_de_page_suivi_d_une_ligne_vide():
    """Une seule ligne blanche en fin de page repousserait le pied de
    page hors de la fenêtre de bord, et il traverserait le filtre."""
    pages = [
        page_realiste(n, ["Du contenu."], pied=f"Acte uniforme de reference {n}") + "\n"
        for n in range(1, 13)
    ]

    conserve = retirer_repetitions(pages[0], reperer_repetitions(pages))

    assert "Acte uniforme de reference" not in conserve


def test_signature_du_generateur_retiree():
    """« Powered by TCPDF » n'apparaît qu'une fois, en fin de document.

    La détection par répétition ne peut donc pas la voir — et sans
    filtre, elle se colle au dernier article : sur l'AUPC, à la suite de
    l'article 258, montrée à l'utilisateur comme du texte officiel.
    """
    page = "Le present Acte uniforme entre en vigueur.\nPowered by TCPDF (www.tcpdf.org)"

    conserve = retirer_repetitions(page, set())

    assert "TCPDF" not in conserve
    assert "entre en vigueur" in conserve


def test_phrase_du_texte_de_loi_au_milieu_de_page_conservee():
    """Le garde-fou de la normalisation par les chiffres.

    La clé ignore tous les chiffres pour reconnaître un pied de page où
    qu'il place son numéro. Deux phrases du texte ne différant que par un
    nombre se confondent donc — « le délai est de quinze jours » et « …de
    trente jours » partagent la même clé une fois les chiffres retirés.
    Seule la position les protège : au milieu d'une page, une ligne n'est
    jamais retirée, quelle que soit sa fréquence.
    """
    milieu = "Le delai court a compter du 15 du mois."
    pages = [page_realiste(n, [milieu]) for n in range(1, 11)]

    conserve = retirer_repetitions(pages[0], reperer_repetitions(pages))

    assert milieu in conserve
    assert "Titre courant" not in conserve


def test_retrait_des_repetitions():
    page = "www.editeur.com OHADA\nArticle 12\nLe capital social est divise."

    resultat = retirer_repetitions(page, {"www.editeur.com OHADA"})

    assert "editeur.com" not in resultat
    assert "Article 12" in resultat


def test_pas_de_retrait_sur_un_document_trop_court():
    """Sur deux ou trois pages, une ligne répétée peut être du contenu :
    l'échantillon est trop petit pour conclure."""
    pages = ["Article 1\nMeme ligne.", "Article 2\nMeme ligne."]

    assert reperer_repetitions(pages) == set()


def test_pied_de_page_numerote_repere():
    """Le défaut qui laissait passer 20 % des articles pollués.

    Un pied de page porte presque toujours le numéro de page : « ...
    général 28 », puis « ... général 29 ». Comparées telles quelles, ces
    lignes sont toutes différentes et AUCUNE n'atteint le seuil de
    répétition — le pied de page traverse alors tout le filtre et se
    retrouve en plein milieu du texte de loi.
    """
    pages = [
        f"Article {n}\nDu contenu.\nActe uniforme portant sur le droit commercial {n}"
        for n in range(1, 11)
    ]

    repetees = reperer_repetitions(pages)

    assert "Acte uniforme portant sur le droit commercial" in repetees
    assert "Acte uniforme" not in retirer_repetitions(pages[0], repetees)
    assert "Article 1" in retirer_repetitions(pages[0], repetees)


def test_pied_de_page_quelle_que_soit_la_place_du_numero():
    """Défaut mesuré sur l'AUSCGIE, et le plus retors des trois.

    Selon la page, l'extraction place le numéro autrement : détaché
    (« …économique 11 »), soudé au dernier mot (« …économique1 1 »), ou
    INSÉRÉ DEDANS (« …économiqu2e » pour la page 2xx). Une règle fondée
    sur la position du chiffre en rate toujours une forme, et le pied de
    page traverse le filtre sur les articles concernés — 220 sur
    l'AUSCGIE.
    """
    variantes = [
        "Acte uniforme relatif au droit des societes 11",
        "Acte uniforme relatif au droit des societes1 1",
        "Acte uniforme relatif au droit des societe2s",
        "Acte uniforme relatif au droit des societes 207",
    ]
    pages = [f"Article {n}\nDu contenu.\n{v}" for n, v in enumerate(variantes * 3, 1)]

    repetees = reperer_repetitions(pages)

    for numero, page in enumerate(pages[:4], 1):
        conserve = retirer_repetitions(page, repetees)
        assert "Acte uniforme" not in conserve
        assert f"Article {numero}" in conserve


def test_entete_d_article_preserve():
    """Le revers du test précédent, et le piège qu'il a révélé.

    « Article 1 », « Article 2 »… se ramènent tous à « Article » si l'on
    retire le nombre final sans précaution. Ils se comptent alors comme
    une seule ligne répétée et le filtre efface les en-têtes d'articles
    du document — un corpus vidé de sa structure.
    """
    pages = [f"Article {n}\nUn contenu propre a l'article {n}." for n in range(1, 11)]

    conserve = retirer_repetitions(pages[0], reperer_repetitions(pages))

    assert "Article 1" in conserve


# ---------------------------------------------------------------------
# Mots coupés en fin de ligne
# ---------------------------------------------------------------------


def test_cesure_typographique_recollee():
    """« commercia-/les » doit redevenir « commerciales ».

    Laissé tel quel, le mot est indexé comme deux jetons : une recherche
    plein texte sur « commerciales » ne trouve pas l'article.
    """
    pages = ["Les societes commercia-\nles sont regies par les societes commerciales."]

    reparees, nombre = recoller_cesures(pages)

    assert "societes commerciales sont regies" in reparees[0]
    assert nombre == 1


def test_vrai_trait_d_union_conserve():
    """« ci-/dessus » n'est pas une césure : le trait appartient au mot.

    Traiter les deux cas de la même façon casse l'un ou l'autre. On
    tranche en interrogeant le document lui-même.
    """
    pages = ["Comme indique ci-\ndessus, la clause ci-dessus est reputee non ecrite."]

    reparees, _ = recoller_cesures(pages)

    assert "ci-dessus, la clause" in reparees[0]


def test_cesure_a_cheval_sur_deux_pages():
    """C'est là que le texte est le plus abîmé : le mot est coupé par la
    fin de page, et le pied de page vient s'intercaler entre les deux
    moitiés. D'où l'ordre : en-têtes retirés AVANT recollage."""
    pages = ["Le present Acte unifor-", "me entre en vigueur. Acte uniforme."]

    reparees, nombre = recoller_cesures(pages)

    assert "Acte uniforme entre en vigueur" in reparees[0]
    assert "unifor-" not in "".join(reparees)
    assert nombre == 1


def test_espace_parasite_apres_le_trait_d_union():
    """Défaut mesuré sur l'AUPC : « juge- commissaire », 36 fois.

    Ce n'est PAS une coupure de fin de ligne — l'extraction rend
    « juge-commissaire » comme deux mots, que le regroupement en lignes
    recolle avec une espace. Le mot le plus fréquent de la procédure
    collective était donc introuvable par une recherche sur son nom.
    """
    pages = [
        "Le juge- commissaire statue. Le juge-commissaire est designe par la juridiction."
    ]

    reparees, nombre = recoller_cesures(pages)

    assert "Le juge-commissaire statue" in reparees[0]
    assert nombre == 1


def test_espace_parasite_sur_une_cesure_typographique():
    """Même défaut, mais sur un mot que le trait d'union ne doit pas
    garder : l'arbitrage est le même, la conclusion inverse."""
    pages = ["Les societes commercia- les et les societes commerciales."]

    reparees, _ = recoller_cesures(pages)

    assert "societes commerciales et" in reparees[0]


def test_mot_compose_inconnu_garde_son_trait():
    """Quand le document ne tranche pas, un préfixe qui ne se soude
    jamais en français garde son trait d'union."""
    pages = ["Les personnes non-\ncommercantes ne sont pas immatriculees."]

    reparees, _ = recoller_cesures(pages)

    assert "non-commercantes" in reparees[0]


# ---------------------------------------------------------------------
# Traitement commun aux deux chemins d'extraction (natif et OCR)
# ---------------------------------------------------------------------


def test_le_nettoyage_commun_retire_entetes_et_recolle_cesures():
    """Le texte issu d'un OCR doit traverser le MEME nettoyage.

    L'OCR ne fait pas disparaitre les titres courants : il les lit, comme
    le reste de la page. Le Journal officiel de l'AUPSRVE repete son
    titre en tete de 115 pages ; sans ce traitement, la ligne se colle
    dans le contenu d'un article sur deux et part a la vectorisation.

    Ce test fige le fait que `nettoyer_pages` fait les deux — retrait des
    repetitions ET recollage des cesures — pour que le chemin OCR n'ait
    rien a reimplementer de son cote.
    """
    # Pages de densité réaliste : sur une page de cinq lignes, tout est un
    # bord, et le filtre de position ne protège plus rien.
    pages = [
        page_realiste(
            n,
            [
                f"Article {n}",
                f"Le present acte {n} regit les procedures commercia-",
                "les applicables aux societes.",
            ],
        )
        for n in range(1, 13)
    ]

    nettoyees, diagnostic = nettoyer_pages(pages)

    entier = "\n".join(nettoyees)
    # L'en-tete courant est parti...
    assert "Titre courant" not in entier
    # ... le contenu est reste, et le mot coupe a ete recolle.
    assert "commerciales" in entier
    assert "commercia-" not in entier
    assert "Article 1" in entier
    assert diagnostic["cesures_recollees"] >= 12


def test_les_traits_manuscrits_sont_retires():
    """Le Journal officiel de l'AUPSRVE est paraphé à la main.

    Même après avoir blanchi l'encre colorée, des résidus de traits
    subsistent que Tesseract rend en charabia, inséré AU MILIEU des
    articles à l'endroit des coupures de page.
    """
    pages = [
        "Le present acte regit les procedures.\n"
        "AD | p FAT # pa Te, A eu Ps 15\n"
        "Il entre en vigueur le 1er janvier.",
    ]

    nettoyees, retirees = retirer_lignes_parasites(pages)

    assert retirees == 1
    assert "FAT" not in nettoyees[0]
    assert "Le present acte regit les procedures." in nettoyees[0]
    assert "Il entre en vigueur le 1er janvier." in nettoyees[0]


def test_en_cas_de_doute_on_garde():
    """LE GARDE-FOU. Un fragment parasite qui passe se voit à la
    relecture ; un alinéa supprimé, non.

    « |) les décisions juridictionnelles » porte une barre verticale —
    un « 1 » mal lu — mais c'est du texte de loi. Il doit survivre.
    """
    pages = [
        "|) les decisions juridictionnelles revetues de la formule executoire\n"
        "vise aux articles 108, 109, alinea |, 114 du present acte uniforme\n"
        "CHAPITRE | LA REQUETE",
    ]

    nettoyees, retirees = retirer_lignes_parasites(pages)

    assert retirees == 0
    assert nettoyees[0] == pages[0]


def test_une_ligne_sans_caractere_impossible_n_est_jamais_touchee():
    pages = ["1)\n- le\nprix.\nArticle 12"]

    nettoyees, retirees = retirer_lignes_parasites(pages)

    assert retirees == 0
    assert nettoyees[0] == pages[0]
