"""Limitation des tentatives de connexion.

CE QUI MANQUAIT. Douze mots de passe faux d'affilee recevaient douze
refus identiques, sans le moindre ralentissement. Rien n'empechait donc
d'essayer un dictionnaire entier contre un compte connu, ni de rejouer
une liste d'identifiants voles contre tous les comptes du service.

Le hachage bcrypt rend chaque essai couteux — c'est deja une defense —
mais il protege le MOT DE PASSE, pas le service : quelques milliers de
tentatives paralellement suffisent a saturer un serveur d'une offre
gratuite, et un mot de passe faible tombe de toute facon.

DEUX COMPTEURS, PARCE QU'UN SEUL LAISSE UN ANGLE MORT.

  par compte  arrete l'acharnement sur une adresse connue — mais pas
              une liste d'identifiants voles, qui n'essaie chaque compte
              qu'une fois.
  par origine arrete cette liste — mais pas un attaquant reparti sur
              plusieurs adresses IP contre un seul compte.

Les deux ensemble couvrent les deux formes, et aucune ne gene un
utilisateur qui se trompe deux ou trois fois.

POURQUOI EN MEMOIRE ET NON EN BASE. Une tentative refusee ne doit pas
couter une ecriture : ce serait offrir un levier d'epuisement a
l'attaquant lui-meme. La contrepartie est assumee : le compteur repart
a zero au redemarrage, et deux instances ne le partagent pas. Sur un
service a une seule instance, cela suffit ; le jour ou il y en aura
plusieurs, il faudra le porter dans un cache partage — et ce commentaire
sera la pour le dire.
"""

from __future__ import annotations

import time
from collections import defaultdict

# DEUX PLAFONDS, ET L'ECART ENTRE EUX EST LE POINT.
#
# Par compte, cinq essais suffisent : au-dela d'une faute de frappe
# repetee, c'est un dictionnaire.
#
# Par origine, il en faut BEAUCOUP PLUS. Une adresse IP publique n'est
# pas une personne : derriere le NAT d'un operateur mobile — la norme au
# Cameroun — comme derriere le reseau d'un bureau ou d'une universite,
# des centaines d'utilisateurs partagent la meme. Appliquer cinq essais
# a l'origine fermait le service a tout un immeuble des qu'une seule
# personne s'y trompait cinq fois. Mesure en conditions reelles :
# le compte d'administration se retrouvait bloque par les echecs d'un
# compte d'essai.
#
# Trente essais laissent respirer un reseau partage tout en arretant
# net une liste d'identifiants voles, qui en demande des milliers.
TENTATIVES_MAX = 5
TENTATIVES_MAX_ORIGINE = 30

# Duree du blocage, et fenetre d'observation. Quinze minutes rendent une
# attaque par dictionnaire irrealisable — quelques centaines d'essais par
# jour — tout en restant supportable pour qui s'est vraiment trompe.
FENETRE = 900.0

# Plafond du nombre de cles retenues. SANS LUI, LE COMPTEUR DEVIENT
# LUI-MEME UNE FAILLE : il suffirait d'envoyer des millions d'adresses
# differentes pour epuiser la memoire du serveur.
CLES_MAX = 10_000

_tentatives: dict[str, list[float]] = defaultdict(list)


def _nettoyer(maintenant: float) -> None:
    """Oublie ce qui est sorti de la fenetre.

    Appele a chaque enregistrement plutot que par une tache de fond :
    une tache de plus serait une piece de plus a surveiller, pour un
    travail qui tient en quelques microsecondes.
    """
    for cle in list(_tentatives):
        recentes = [t for t in _tentatives[cle] if maintenant - t < FENETRE]
        if recentes:
            _tentatives[cle] = recentes
        else:
            del _tentatives[cle]


def _plafond(cle: str) -> int:
    """Le nombre d'essais tolere pour cette cle.

    Le prefixe porte l'information : une cle « origine: » designe une
    adresse IP, potentiellement partagee par des centaines de personnes,
    et ne peut pas etre traitee comme un compte nominatif.
    """
    return TENTATIVES_MAX_ORIGINE if cle.startswith("origine:") else TENTATIVES_MAX


def secondes_restantes(cles: list[str]) -> int:
    """0 si la connexion est permise, sinon l'attente en secondes.

    On rend l'attente plutot qu'un booleen : un message qui dit
    « reessayez dans 12 minutes » evite a l'utilisateur legitime de
    croire son compte perdu, et n'apprend rien d'utile a un attaquant —
    qui constate de toute facon le refus.
    """
    maintenant = time.monotonic()
    attente = 0
    for cle in cles:
        recentes = [t for t in _tentatives.get(cle, []) if maintenant - t < FENETRE]
        if len(recentes) >= _plafond(cle):
            attente = max(attente, int(FENETRE - (maintenant - recentes[0])) + 1)
    return attente


def enregistrer_echec(cles: list[str]) -> None:
    """Compte une tentative ratee sur chacune des cles."""
    maintenant = time.monotonic()

    if len(_tentatives) > CLES_MAX:
        _nettoyer(maintenant)
        # Toujours plein apres nettoyage : on est sous saturation
        # deliberee. On cesse d'enregistrer plutot que de grossir sans
        # fin — les cles deja suivies restent protegees.
        if len(_tentatives) > CLES_MAX:
            return

    for cle in cles:
        _tentatives[cle].append(maintenant)


def effacer(cles: list[str]) -> None:
    """Remet les compteurs a zero apres une connexion reussie.

    Sans cela, quelqu'un qui se trompe quatre fois puis reussit resterait
    a un essai du blocage pendant un quart d'heure.
    """
    for cle in cles:
        _tentatives.pop(cle, None)
