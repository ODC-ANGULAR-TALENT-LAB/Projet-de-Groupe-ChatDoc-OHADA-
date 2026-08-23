"""Limitation des tentatives de connexion.

CE QUI MANQUAIT. Douze mots de passe faux d'affilee recevaient douze
refus identiques, sans le moindre ralentissement : rien n'empechait
d'essayer un dictionnaire entier contre un compte connu, ni de rejouer
une liste d'identifiants voles contre tous les comptes.

Le hachage bcrypt rend chaque essai couteux, mais il protege le MOT DE
PASSE, pas le service : un mot de passe faible tombe de toute facon, et
quelques milliers d'essais paralleles saturent un serveur d'offre
gratuite.
"""

import pytest

from app.services import cadence


@pytest.fixture(autouse=True)
def compteur_vierge():
    """Chaque cas part d'une ardoise propre.

    Le compteur vit en memoire du processus : sans cette remise a zero,
    un cas laisserait des tentatives derriere lui et le suivant echouerait
    pour une raison qui ne le concerne pas.
    """
    cadence._tentatives.clear()
    yield
    cadence._tentatives.clear()


def test_les_premieres_tentatives_passent():
    cles = ["compte:paul@exemple.cm"]
    for _ in range(cadence.TENTATIVES_MAX - 1):
        assert cadence.secondes_restantes(cles) == 0
        cadence.enregistrer_echec(cles)
    assert cadence.secondes_restantes(cles) == 0


def test_le_blocage_survient_au_plafond():
    cles = ["compte:paul@exemple.cm"]
    for _ in range(cadence.TENTATIVES_MAX):
        cadence.enregistrer_echec(cles)
    assert cadence.secondes_restantes(cles) > 0


def test_une_reussite_efface_l_ardoise():
    """Quatre erreurs puis une reussite ne doivent pas laisser au bord
    du blocage pendant un quart d'heure."""
    cles = ["compte:paul@exemple.cm"]
    for _ in range(cadence.TENTATIVES_MAX - 1):
        cadence.enregistrer_echec(cles)
    cadence.effacer(cles)

    for _ in range(cadence.TENTATIVES_MAX - 1):
        assert cadence.secondes_restantes(cles) == 0
        cadence.enregistrer_echec(cles)


def test_deux_comptes_ont_des_compteurs_separes():
    """UN SEUL COMPTEUR GLOBAL FERMERAIT LE SERVICE A TOUT LE MONDE.

    C'est exactement ce qui se produirait derriere un mandataire sans
    `--proxy-headers` : toutes les requetes portant la meme adresse, cinq
    echecs par cinq personnes differentes bloqueraient la connexion pour
    l'ensemble des visiteurs.
    """
    for _ in range(cadence.TENTATIVES_MAX):
        cadence.enregistrer_echec(["compte:paul@exemple.cm"])

    assert cadence.secondes_restantes(["compte:paul@exemple.cm"]) > 0
    assert cadence.secondes_restantes(["compte:marie@exemple.cm"]) == 0


def test_l_origine_bloque_une_liste_d_identifiants_voles():
    """LE COMPTEUR PAR COMPTE NE SUFFIT PAS.

    Une attaque par liste d'identifiants voles n'essaie chaque compte
    qu'une fois : aucun compteur par compte ne la verrait. C'est le
    compteur par origine qui l'arrete.
    """
    origine = "origine:203.0.113.7"
    for n in range(cadence.TENTATIVES_MAX_ORIGINE):
        cadence.enregistrer_echec([f"compte:victime{n}@exemple.cm", origine])

    # Un compte jamais essaye, mais depuis la meme origine.
    assert cadence.secondes_restantes(["compte:neuf@exemple.cm", origine]) > 0


def test_le_compteur_ne_grossit_pas_sans_fin():
    """SANS PLAFOND, LE COMPTEUR EST LUI-MEME UNE FAILLE.

    Il suffirait d'envoyer des millions d'adresses differentes pour
    epuiser la memoire du serveur — une denegation de service offerte
    par la protection elle-meme.
    """
    for n in range(cadence.CLES_MAX + 500):
        cadence.enregistrer_echec([f"origine:10.0.{n // 256}.{n % 256}"])

    assert len(cadence._tentatives) <= cadence.CLES_MAX + 1


def test_l_attente_annoncee_est_plausible():
    """Le message dit « reessayez dans N minutes » : N doit tenir debout."""
    cles = ["compte:paul@exemple.cm"]
    for _ in range(cadence.TENTATIVES_MAX):
        cadence.enregistrer_echec(cles)

    attente = cadence.secondes_restantes(cles)
    assert 0 < attente <= cadence.FENETRE + 1


def test_un_reseau_partage_ne_bloque_pas_tout_le_monde():
    """LE DEFAUT DE CONCEPTION QUE CE PLAFOND CORRIGE.

    Une adresse IP publique n'est pas une personne : derriere le NAT
    d'un operateur mobile, des centaines d'utilisateurs partagent la
    meme. Avec un plafond unique, cinq erreurs d'une seule personne
    fermaient le service a tous les autres — constate en conditions
    reelles : le compte d'administration bloque par les echecs d'un
    compte d'essai.
    """
    origine = "origine:41.202.0.5"
    for _ in range(cadence.TENTATIVES_MAX):
        cadence.enregistrer_echec(["compte:maladroit@exemple.cm", origine])

    assert cadence.secondes_restantes(["compte:maladroit@exemple.cm", origine]) > 0
    assert cadence.secondes_restantes(["compte:voisin@exemple.cm", origine]) == 0
