"""Forfaits, credits d'usage, et la marge qu'ils doivent degager.

UN CREDIT = UNE QUESTION A L'ASSISTANT. Consulter la bibliotheque,
chercher dans le corpus, ouvrir un article ou utiliser un calculateur
ne coute rien : ces gestes n'appellent aucun modele. Seule la synthese
redigee consomme, parce qu'elle seule se paie au jeton.

D'OU VIENT LE COUT D'UNE QUESTION. Il est mesurable, et il l'a ete sur
ce corpus plutot que suppose :

  - contexte : `nb_articles_contexte` articles, 584 caracteres en
    moyenne dans cette base, plus leur en-tete de numerotation ;
  - prompt systeme : 1046 caracteres ;
  - question, fil de conversation et schema de sortie impose ;
  - reponse : plafonnee a `llm_max_tokens`, en pratique bien moindre.

Soit de l'ordre de 2 500 jetons en entree et 800 en sortie. Le prix du
millier de jetons depend du fournisseur et change avec lui : il n'est
donc PAS code en dur ici mais lu dans la configuration
(`cout_question_fcfa`), avec l'embedding de la question inclus.

LA MARGE EST UNE CONTRAINTE, PAS UNE INTENTION. Un forfait dont les
credits coutent plus que son prix fait perdre de l'argent a chaque
vente, et rien dans le code ne le signalerait. `marge` calcule cette
marge, et un test refuse tout forfait payant qui descendrait sous
`MARGE_MINIMALE`. Changer le nombre de credits sans revoir le prix
casse donc la suite de tests au lieu de casser le compte en banque.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import parametres

# Plancher de marge exige sur les forfaits payants. En dessous, la
# vente ne couvre plus les frais qui n'apparaissent pas dans le cout au
# jeton : hebergement, base de donnees, commission de l'operateur de
# paiement mobile, et les questions offertes aux comptes gratuits.
MARGE_MINIMALE = 0.50


@dataclass(frozen=True)
class Forfait:
    code: str
    libelle: str
    prix_fcfa: int
    credits: int
    argumentaire: str
    # Ce que le forfait apporte, dit en clair. Sert l'interface, et
    # oblige a formuler ce qu'on vend.
    atouts: tuple[str, ...]

    # FORFAIT D'ESSAI : il sert a eprouver la chaine de paiement de bout
    # en bout, pas a etre vendu. Il est donc EXCLU du plancher de marge —
    # un montant symbolique ne peut pas la respecter, et l'y soumettre
    # obligerait a truquer le chiffre du cout pour faire passer le test.
    #
    # Il n'apparait au catalogue QUE lorsque CamPay tourne en
    # demonstration. En production il disparait de lui-meme : personne ne
    # peut souscrire par megarde un forfait a 25 F, et il n'y a aucun
    # drapeau a penser a refermer avant la mise en ligne.
    essai: bool = False

    @property
    def cout_variable_fcfa(self) -> float:
        """Ce que coutent les credits s'ils sont tous consommes.

        On raisonne sur la consommation TOTALE, pas moyenne : un
        forfait doit rester rentable meme face a l'utilisateur qui
        epuise ses credits, sinon la rentabilite ne tient que parce que
        les clients n'utilisent pas ce qu'ils ont paye.
        """
        return self.credits * parametres.cout_question_fcfa

    @property
    def marge(self) -> float | None:
        """Marge brute, entre 0 et 1. `None` pour le forfait gratuit.

        Le gratuit n'a pas de marge a calculer : c'est un cout
        d'acquisition assume, pas une vente ratee.
        """
        if self.prix_fcfa == 0:
            return None
        return (self.prix_fcfa - self.cout_variable_fcfa) / self.prix_fcfa


# ---------------------------------------------------------------------
# Le catalogue
#
# TROIS FORFAITS VENDUS, ET PAS DAVANTAGE. Au-dela, le choix devient un
# travail : l'utilisateur compare des colonnes au lieu de se decider.
# Trois lignes se lisent d'un coup d'oeil — decouvrir, travailler,
# equiper un cabinet.
#
# Le quatrieme, « essai », n'est pas vendu : c'est un montant symbolique
# qui sert a eprouver la chaine de paiement, et il disparait du
# catalogue en production (voir catalogue_visible).
#
# Les volumes ne sont pas ronds par hasard : ils sont le plus grand
# nombre de credits qui laisse la marge au-dessus du plancher, arrondi
# vers le bas. Arrondir vers le haut aurait mieux sonne et grignote la
# marge a chaque vente.
# ---------------------------------------------------------------------

FORFAITS: tuple[Forfait, ...] = (
    Forfait(
        code="gratuit",
        libelle="Découverte",
        prix_fcfa=0,
        credits=10,
        argumentaire="De quoi juger l'outil sur vos propres dossiers.",
        atouts=(
            "10 questions par mois",
            "Bibliothèque, recherche et calculateurs sans limite",
            "Chaque réponse cite ses articles",
        ),
    ),
    Forfait(
        code="essentiel",
        libelle="Essentiel",
        prix_fcfa=5000,
        credits=90,
        argumentaire="Pour un praticien qui consulte le corpus chaque jour.",
        atouts=(
            "90 questions par mois",
            "Export PDF sourcé de vos réponses",
            "Favoris, annotations et veille sur les textes suivis",
        ),
    ),
    Forfait(
        code="cabinet",
        libelle="Cabinet",
        prix_fcfa=8000,
        credits=150,
        argumentaire="Pour un rythme soutenu et les dossiers à plusieurs textes.",
        atouts=(
            "150 questions par mois",
            "Tout ce que contient Essentiel",
            "Analyse de conformité et générateur de documents",
        ),
    ),
    Forfait(
        code="essai",
        libelle="Essai (test technique)",
        prix_fcfa=25,
        credits=2,
        argumentaire=(
            "Montant symbolique pour éprouver la chaîne de paiement. "
            "Ce forfait n'est pas destiné à la vente."
        ),
        atouts=(
            "2 questions, le temps de vérifier que tout fonctionne",
            "Débit réel de 25 FCFA sur le compte Mobile Money",
            "Visible uniquement hors production",
        ),
        essai=True,
    ),
)

PAR_CODE = {forfait.code: forfait for forfait in FORFAITS}


def catalogue_visible() -> tuple[Forfait, ...]:
    """Les forfaits proposes aux utilisateurs.

    Le forfait d'essai n'y figure QUE hors production. En production il
    disparait de lui-meme : personne ne peut le souscrire par megarde,
    et il n'y a aucun drapeau a penser a refermer avant la mise en
    ligne. Il reste connu de PAR_CODE, pour qu'un abonnement souscrit
    pendant les essais continue de s'afficher correctement.
    """
    en_demonstration = parametres.campay_environnement.lower() not in {
        "prod",
        "production",
        "live",
    }
    return tuple(f for f in FORFAITS if not f.essai or en_demonstration)


# Conserve pour le code existant, qui lit le quota par plan.
QUOTA_PAR_PLAN = {forfait.code: forfait.credits for forfait in FORFAITS}


def forfait(code: str) -> Forfait:
    """Le forfait, ou le gratuit si le code est inconnu.

    Retomber sur le gratuit plutot que lever : un plan inconnu en base —
    renommage, migration ratee — ne doit pas empecher quelqu'un de se
    connecter. Il perd des credits, il ne perd pas son compte.
    """
    return PAR_CODE.get(code, PAR_CODE["gratuit"])


def credits_du_plan(code: str) -> int:
    return forfait(code).credits
