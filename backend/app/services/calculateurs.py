"""Calculateurs fiscaux adosses aux articles du Code general des impots.

CE QUE LE CAHIER DES CHARGES DEMANDE (§5, §14) : « des calculateurs
fiscaux relies aux articles qui les fondent », et la user story « en
tant que DAF, je veux calculer un IS avec le detail des articles
appliques afin de justifier le calcul ».

LE MOT IMPORTANT EST « JUSTIFIER ». Un resultat sans sa base legale n'a
aucune valeur pour le professionnel qui devra le defendre : c'est un
chiffre. Avec l'article, c'est une piece de travail. Chaque ligne du
resultat porte donc l'article qui la fonde, et son extrait officiel.

---------------------------------------------------------------------
LE TAUX N'EST PAS ECRIT DANS CE FICHIER. IL EST LU DANS LE CORPUS.
---------------------------------------------------------------------

Un taux code en dur se perime a la premiere loi de finances, en
silence, et l'outil continue de repondre avec assurance. C'est le pire
defaut possible ici : personne ne verifie un chiffre qui s'affiche
comme avant.

On declare donc, pour chaque parametre, L'ARTICLE QUI LE PORTE et la
valeur qu'on s'attend a y trouver. Au moment du calcul, l'article est
relu en base et la valeur y est CHERCHEE :

  - si elle y figure, le calcul se fait, et l'extrait accompagne le
    resultat ;
  - si elle n'y figure plus — loi de finances, correction du corpus —
    LE CALCUL EST REFUSE, avec le motif.

La declaration n'est donc pas la source de verite : c'est une
affirmation que le corpus valide ou dement. Un taux qui change casse
bruyamment au lieu de mentir discretement.

CE QUE CES OUTILS NE SONT PAS. Ni un logiciel de paie, ni une
declaration fiscale, ni un conseil. Le cahier des charges (§3) exclut
explicitement toute garantie de resultat. On applique un taux a une
base, en montrant d'ou vient le taux.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.orm import Session


class CalculRefuse(RuntimeError):
    """Le calcul ne peut pas etre fait, et on dit pourquoi."""


# Le corpus fiscal disponible. LA LISTE DES PAYS SUIT LE CORPUS, elle ne
# le precede pas : la maquette proposait la Cote d'Ivoire et le Senegal,
# dont nous n'avons aucun code. Les offrir promettrait une source qu'on
# n'a pas, et l'utilisateur ne s'en apercevrait qu'apres coup.
PAYS = "CM"
SIGLE_CGI = "CGI"


@dataclass(frozen=True)
class Parametre:
    """Une valeur chiffree, et l'article qui la porte.

    `valeur` est ce qu'on s'attend a lire dans l'article ; `motif` est
    la facon dont elle s'y ecrit, car une meme valeur se redige de
    plusieurs manieres (« 19,25 % », « 19,25% », « 19.25 pour cent »).
    """

    cle: str
    libelle: str
    valeur: Decimal
    numero_article: str
    motif: re.Pattern


def taux(cle: str, libelle: str, pourcentage: str, numero_article: str) -> Parametre:
    """Declare un taux exprime en pourcentage.

    Le motif tolere la virgule ET le point decimaux, l'espace avant le
    signe pourcent, et l'espace insecable — trois variantes rencontrees
    dans le meme code selon les articles.

    LES DEUX FRONTIERES NE SONT PAS DECORATIVES. Sans celle de gauche,
    chercher « 19,25 » trouve « 119,25 » ; sans celle de droite,
    chercher « 33 » trouve « 33,5 ». Dans les deux cas le garde-fou
    validerait un taux que l'article ne porte pas — c'est-a-dire
    exactement ce qu'il est cense empecher.
    """
    entier, _, decimales = pourcentage.partition(",")
    chiffres = re.escape(entier) + (
        rf"[.,]{re.escape(decimales)}(?!\d)" if decimales else r"(?![.,]?\d)"
    )
    return Parametre(
        cle=cle,
        libelle=libelle,
        valeur=Decimal(pourcentage.replace(",", ".")),
        numero_article=numero_article,
        motif=re.compile(rf"(?<![\d.,]){chiffres}\s*(?:%|pour\s*cent)", re.I),
    )


def lire_article(session: Session, numero: str) -> dict:
    """Contenu de l'article du CGI en vigueur, ou refus explicite."""
    ligne = session.execute(
        text(
            "SELECT a.numero, a.chemin, a.contenu "
            "FROM article a JOIN texte t ON t.id = a.texte_id "
            "WHERE t.sigle = :sigle AND a.numero = :numero "
            "  AND a.date_abrogation IS NULL "
            "LIMIT 1"
        ),
        {"sigle": SIGLE_CGI, "numero": numero},
    ).mappings().first()

    if ligne is None:
        raise CalculRefuse(
            f"L'article {numero} du {SIGLE_CGI} est absent du corpus. "
            "Le calcul n'a pas de base légale vérifiable : il est refusé."
        )
    return dict(ligne)


def verifier(session: Session, parametre: Parametre) -> dict:
    """Confronte la valeur declaree a l'article qui doit la porter.

    Rend la base legale a joindre au resultat. Leve CalculRefuse si
    l'article ne porte plus cette valeur — c'est le garde-fou contre un
    bareme perime.
    """
    article = lire_article(session, parametre.numero_article)

    if not parametre.motif.search(article["contenu"]):
        raise CalculRefuse(
            f"L'article {parametre.numero_article} du {SIGLE_CGI} ne mentionne "
            f"plus « {parametre.libelle} » à {parametre.valeur} %. Le barème a "
            "probablement changé. Le calcul est refusé tant que le paramètre "
            "n'a pas été remis en accord avec le texte."
        )

    return {
        "libelle": parametre.libelle,
        "valeur": str(parametre.valeur),
        "sigle": SIGLE_CGI,
        "numero": article["numero"],
        "chemin": article["chemin"],
        "extrait": article["contenu"],
    }


def arrondir(montant: Decimal) -> Decimal:
    """Au franc CFA : la monnaie n'a pas de subdivision en usage."""
    return montant.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def montant_valide(brut) -> Decimal:
    """Base imposable exploitable, ou refus.

    Un montant negatif ou absurde n'est pas une erreur de calcul mais
    une erreur de saisie : on la renvoie a l'utilisateur plutot que de
    produire un resultat qui aurait l'air d'un resultat.
    """
    try:
        montant = Decimal(str(brut))
    except (InvalidOperation, ValueError, TypeError) as erreur:
        raise CalculRefuse("Le montant saisi n'est pas un nombre.") from erreur

    if not montant.is_finite() or montant < 0:
        raise CalculRefuse("Le montant doit être positif.")
    if montant > Decimal("1e15"):
        raise CalculRefuse("Le montant dépasse ce que cet outil sait traiter.")
    return montant


CENT = Decimal("100")


def _ligne(libelle: str, montant: Decimal, base_legale: dict | None = None) -> dict:
    """Une ligne du resultat, avec l'article qui la fonde s'il y en a un.

    Toutes les lignes n'en ont pas : une base saisie par l'utilisateur
    ne se fonde sur aucun article, et pretendre le contraire serait
    fabriquer une reference.
    """
    ligne = {"libelle": libelle, "montant": str(arrondir(montant))}
    if base_legale:
        ligne["base_legale"] = base_legale
    return ligne


def calculer_tva(
    session: Session,
    montant,
    sur_ttc: bool,
    parametre: Parametre,
    centimes: Parametre | None = None,
) -> dict:
    """Liquidation de la TVA, a partir d'un montant HT ou TTC.

    LES DEUX SENS SONT UTILES ET PAS SYMETRIQUES. Le comptable part du
    HT quand il facture, du TTC quand il ventile une depense deja
    reglee. Retrancher naivement le taux d'un TTC est l'erreur
    classique : sur 119,25, retirer 19,25 % donne 96,26 et non 100.
    """
    base = montant_valide(montant)
    legale = verifier(session, parametre)
    coefficient = parametre.valeur / CENT

    # LES CENTIMES ADDITIONNELS COMMUNAUX FONT PARTIE DE CE QUE PAIE LE
    # REDEVABLE. L'article C 53 les institue sur la TVA, l'IRPP et l'IS ;
    # l'article C 54 en fixe le taux a 10 % du principal. Rendre le seul
    # taux de l'article 142 donnerait un chiffre exact mais inutilisable :
    # ce n'est pas la somme que l'entreprise verse.
    #
    # Ils sont montres SUR UNE LIGNE SEPAREE, avec leur propre article.
    # Les fondre dans un taux unique de 19,25 % ferait apparaitre un
    # chiffre qu'aucun article du Code ne porte — donc invérifiable.
    legale_centimes = verifier(session, centimes) if centimes else None
    if centimes:
        coefficient *= Decimal(1) + centimes.valeur / CENT

    if sur_ttc:
        hors_taxes = base / (Decimal(1) + coefficient)
        taxe = base - hors_taxes
        toutes_taxes = base
    else:
        hors_taxes = base
        taxe = base * coefficient
        toutes_taxes = base + taxe

    principal = hors_taxes * parametre.valeur / CENT
    lignes = [
        _ligne("Base imposable (HT)", hors_taxes),
        _ligne(f"{parametre.libelle} ({parametre.valeur} %)", principal, legale),
    ]
    if centimes:
        lignes.append(
            _ligne(
                f"{centimes.libelle} ({centimes.valeur} % du principal)",
                taxe - principal,
                legale_centimes,
            )
        )
    lignes.append(_ligne("Montant toutes taxes comprises (TTC)", toutes_taxes))

    return {
        "intitule": "Taxe sur la valeur ajoutée",
        "lignes": lignes,
        "resultat": {
            "libelle": "Montant de la TVA (centimes compris)"
            if centimes
            else "Montant de la TVA",
            "montant": str(arrondir(taxe)),
        },
    }


def calculer_impot_proportionnel(
    session: Session,
    montant,
    parametre: Parametre,
    intitule: str,
    libelle_base: str,
    centimes: Parametre | None = None,
) -> dict:
    """Impot assis sur une base, a taux unique.

    Couvre l'IS et les taxes proportionnelles : la structure est la
    meme, seuls le taux et l'article changent — donc la configuration,
    pas le code.
    """
    base = montant_valide(montant)
    legale = verifier(session, parametre)
    principal = base * parametre.valeur / CENT

    lignes = [
        _ligne(libelle_base, base),
        _ligne(f"{parametre.libelle} ({parametre.valeur} %)", principal, legale),
    ]

    total = principal
    if centimes:
        # Meme raison que pour la TVA : ce que l'entreprise verse
        # comprend les centimes additionnels communaux, sur une ligne
        # separee et avec l'article qui les fonde.
        legale_centimes = verifier(session, centimes)
        supplement = principal * centimes.valeur / CENT
        total += supplement
        lignes.append(
            _ligne(
                f"{centimes.libelle} ({centimes.valeur} % du principal)",
                supplement,
                legale_centimes,
            )
        )

    return {
        "intitule": intitule,
        "lignes": lignes,
        "resultat": {
            "libelle": f"{intitule} (centimes compris)" if centimes else intitule,
            "montant": str(arrondir(total)),
        },
    }


# ---------------------------------------------------------------------
# Bareme progressif
#
# L'IRPP des salaries ne s'applique pas a taux unique : l'article 69 du
# CGI le calcule par tranches. Un taux moyen unique serait faux pour
# tout le monde sauf par hasard.
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class Tranche:
    """Une tranche du bareme : jusqu'a `plafond`, au taux `taux`.

    `plafond` a None pour la derniere tranche, celle qui n'est pas
    bornee. Un plafond invente — un tres grand nombre — se retrouverait
    affiche a l'utilisateur comme s'il figurait dans la loi.
    """

    plafond: Decimal | None
    taux: Decimal


@dataclass(frozen=True)
class Bareme:
    """Un bareme progressif, et l'article qui le porte."""

    cle: str
    libelle: str
    tranches: tuple[Tranche, ...]
    numero_article: str


def bareme(cle: str, libelle: str, tranches: list[tuple[str | None, str]],
           numero_article: str) -> Bareme:
    """Declare un bareme : [(plafond, taux), ...], plafond None a la fin."""
    return Bareme(
        cle=cle,
        libelle=libelle,
        numero_article=numero_article,
        tranches=tuple(
            Tranche(
                plafond=None if plafond is None else Decimal(plafond),
                taux=Decimal(taux.replace(",", ".")),
            )
            for plafond, taux in tranches
        ),
    )


def _motif_montant(montant: Decimal) -> re.Pattern:
    """Reconnait un montant quels que soient ses separateurs de milliers.

    « 2000000 » s'ecrit « 2 000 000 » dans le Code, parfois avec une
    espace insecable, parfois avec un point. On accepte n'importe quel
    separateur ENTRE les groupes de chiffres, et aucun autre.
    """
    chiffres = str(int(montant))
    return re.compile(r"[\s.,\u00a0]*".join(chiffres))


def verifier_bareme(session: Session, declare: Bareme) -> dict:
    """Confronte CHAQUE tranche a l'article qui doit la porter.

    ON VERIFIE LES TAUX ET LES SEUILS. Un bareme dont les taux seraient
    justes mais les seuils perimes donnerait des resultats faux sans
    qu'aucun controle ne bronche — et c'est le cas le plus frequent,
    puisqu'une loi de finances deplace plus souvent les tranches
    qu'elle n'en change les taux.
    """
    article = lire_article(session, declare.numero_article)
    contenu = article["contenu"]

    for tranche in declare.tranches:
        motif = taux("t", "", str(tranche.taux).replace(".", ","), "").motif
        if not motif.search(contenu):
            raise CalculRefuse(
                f"L'article {declare.numero_article} du {SIGLE_CGI} ne "
                f"mentionne plus le taux de {tranche.taux} %. Le barème a "
                "probablement changé : le calcul est refusé."
            )
        if tranche.plafond is not None and not _motif_montant(
            tranche.plafond
        ).search(contenu):
            raise CalculRefuse(
                f"L'article {declare.numero_article} du {SIGLE_CGI} ne "
                f"mentionne plus le seuil de {int(tranche.plafond):,} FCFA "
                "— le barème a probablement changé.".replace(",", " ")
            )

    return {
        "libelle": declare.libelle,
        "valeur": "barème progressif",
        "sigle": SIGLE_CGI,
        "numero": article["numero"],
        "chemin": article["chemin"],
        "extrait": contenu,
    }


def calculer_impot_progressif(
    session: Session,
    montant,
    declare: Bareme,
    intitule: str,
    libelle_base: str,
    centimes: Parametre | None = None,
) -> dict:
    """Applique un bareme tranche par tranche.

    CHAQUE TRANCHE EST UNE LIGNE DU RESULTAT. Rendre le seul total
    obligerait le professionnel a refaire le calcul pour le verifier,
    ce qui est exactement ce que l'outil doit lui epargner.
    """
    base = montant_valide(montant)
    legale = verifier_bareme(session, declare)

    lignes = [_ligne(libelle_base, base)]
    total = Decimal(0)
    plancher = Decimal(0)
    premiere = True

    for tranche in declare.tranches:
        haut = tranche.plafond if tranche.plafond is not None else base
        assiette = max(Decimal(0), min(base, haut) - plancher)
        if assiette > 0:
            part = assiette * tranche.taux / CENT
            total += part
            borne = (
                f"jusqu'à {int(tranche.plafond):,}".replace(",", " ")
                if tranche.plafond is not None
                else f"au-delà de {int(plancher):,}".replace(",", " ")
            )
            lignes.append(
                _ligne(
                    f"{borne} FCFA — {tranche.taux} %",
                    part,
                    # L'article n'est rattache qu'a la PREMIERE tranche :
                    # le repeter a chaque ligne afficherait cinq fois le
                    # meme extrait sous le meme resultat.
                    legale if premiere else None,
                )
            )
            premiere = False
        if tranche.plafond is None:
            break
        plancher = tranche.plafond

    if centimes:
        legale_centimes = verifier(session, centimes)
        supplement = total * centimes.valeur / CENT
        lignes.append(
            _ligne(
                f"{centimes.libelle} ({centimes.valeur} % du principal)",
                supplement,
                legale_centimes,
            )
        )
        total += supplement

    return {
        "intitule": intitule,
        "lignes": lignes,
        "resultat": {
            "libelle": f"{intitule} (centimes compris)" if centimes else intitule,
            "montant": str(arrondir(total)),
        },
    }


# ---------------------------------------------------------------------
# Tarif encadre (contribution des patentes)
#
# L'article C 13 du CGI liquide la patente par un taux sur le chiffre
# d'affaires, PLAFONNE ET PLANCHONNE selon la taille de l'entreprise.
# Rendre le seul produit du taux serait faux dans les deux queues de la
# distribution — c'est-a-dire pour les tres petites et les tres grandes,
# justement celles ou l'encadrement mord.
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class Tarif:
    """Un taux encadre, pour une categorie d'entreprise."""

    categorie: str
    libelle: str
    taux: Decimal
    plancher: Decimal
    plafond: Decimal
    numero_article: str
    # Le plafond s'ecrit parfois en toutes lettres dans le Code
    # (« 2,5 milliards »). On garde l'ecriture de l'article pour
    # pouvoir l'y retrouver : chercher « 2500000000 » echouerait.
    plafond_ecrit: str


def tarif(
    categorie: str,
    libelle: str,
    taux_: str,
    plancher: str,
    plafond: str,
    plafond_ecrit: str,
    numero_article: str,
) -> Tarif:
    return Tarif(
        categorie=categorie,
        libelle=libelle,
        taux=Decimal(taux_.replace(",", ".")),
        plancher=Decimal(plancher),
        plafond=Decimal(plafond),
        plafond_ecrit=plafond_ecrit,
        numero_article=numero_article,
    )


def verifier_tarif(session: Session, declare: Tarif) -> dict:
    """Confronte taux, plancher et plafond a l'article qui les porte."""
    article = lire_article(session, declare.numero_article)
    contenu = article["contenu"]

    motif_taux = taux("t", "", str(declare.taux).replace(".", ","), "").motif
    if not motif_taux.search(contenu):
        raise CalculRefuse(
            f"L'article {declare.numero_article} du {SIGLE_CGI} ne mentionne "
            f"plus le taux de {declare.taux} % pour {declare.libelle}. "
            "Le tarif a probablement changé : le calcul est refusé."
        )

    if not _motif_montant(declare.plancher).search(contenu):
        raise CalculRefuse(
            f"L'article {declare.numero_article} du {SIGLE_CGI} ne mentionne "
            f"plus le plancher de {int(declare.plancher):,} FCFA.".replace(",", " ")
        )

    if not re.search(
        r"[\s.,\u00a0]*".join(re.escape(c) for c in declare.plafond_ecrit if not c.isspace()),
        contenu,
        re.I,
    ):
        raise CalculRefuse(
            f"L'article {declare.numero_article} du {SIGLE_CGI} ne mentionne "
            f"plus le plafond de {declare.plafond_ecrit}."
        )

    return {
        "libelle": declare.libelle,
        "valeur": str(declare.taux),
        "sigle": SIGLE_CGI,
        "numero": article["numero"],
        "chemin": article["chemin"],
        "extrait": contenu,
    }


def calculer_patente(session: Session, montant, declare: Tarif) -> dict:
    """Contribution des patentes : taux sur le chiffre d'affaires, encadre.

    AUCUN CENTIME N'EST AJOUTE ICI, et ce n'est pas un oubli. L'alinea 2
    de l'article C 13 precise que le montant ainsi determine « comprend
    outre le principal de la patente, la taxe de developpement local,
    les centimes additionnels au profit des chambres consulaires et la
    redevance audiovisuelle ». Y ajouter les centimes communaux les
    compterait deux fois.
    """
    base = montant_valide(montant)
    legale = verifier_tarif(session, declare)

    theorique = base * declare.taux / CENT
    retenu = min(max(theorique, declare.plancher), declare.plafond)

    lignes = [
        _ligne("Chiffre d'affaires du dernier exercice clos", base),
        _ligne(f"{declare.libelle} — {declare.taux} %", theorique, legale),
    ]

    # ON DIT QUAND L'ENCADREMENT A JOUE. Un montant qui ne correspond pas
    # au taux affiche, sans explication, ressemble a une erreur de
    # calcul — alors que c'est la loi qui l'impose.
    if theorique < declare.plancher:
        lignes.append(
            _ligne(
                f"Plancher applique ({int(declare.plancher):,} FCFA)".replace(",", " "),
                retenu,
            )
        )
    elif theorique > declare.plafond:
        lignes.append(
            _ligne(f"Plafond appliqué ({declare.plafond_ecrit})", retenu)
        )

    return {
        "intitule": "Contribution des patentes",
        "lignes": lignes,
        "resultat": {
            "libelle": "Contribution des patentes",
            "montant": str(arrondir(retenu)),
        },
    }
