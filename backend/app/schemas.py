"""Schemas Pydantic : le contrat d'entree et de sortie de l'API.

Ces schemas sont aussi la base des interfaces TypeScript du frontend
(phase F). Tout changement ici se repercute cote Angular.
"""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Niveaux de confiance que le modele est autorise a rendre.
Confiance = Literal["elevee", "moyenne", "insuffisante"]


# ---------------------------------------------------------------------
# Comptes
# ---------------------------------------------------------------------


class Identifiants(BaseModel):
    """Identifiants de connexion.

    Pas de case a cocher ici : on ne redemande pas d'accepter les
    conditions a chaque connexion. L'acceptation est enregistree une
    fois, a l'inscription, avec sa date et sa version.
    """

    email: EmailStr
    mot_de_passe: str = Field(min_length=8, max_length=200)


class Inscription(Identifiants):
    """Creation de compte : les conditions doivent etre acceptees.

    LE DEFAUT EST FALSE, ET IL N'Y A PAS DE VALEUR PAR DEFAUT COTE
    SERVEUR. Un client qui omet le champ se voit refuser l'inscription
    plutot que consentir a la place de l'utilisateur.
    """

    cgu_acceptees: bool = False
    # Facultatif : on peut s'inscrire sans le donner et le renseigner
    # plus tard depuis les paramètres.
    prenom: str | None = Field(default=None, max_length=60)


class JetonGoogle(BaseModel):
    """Jeton d'identite obtenu par le navigateur aupres de Google.

    `cgu_acceptees` n'est exige QUE si le compte n'existe pas encore :
    Google sert a la fois a s'inscrire et a se connecter, et redemander
    l'acceptation a chaque connexion la ferait cocher sans lire.
    """

    jeton_identite: str = Field(min_length=20)
    cgu_acceptees: bool = False


class Jeton(BaseModel):
    jeton_acces: str
    type_jeton: str = "bearer"
    expire_dans_minutes: int


class Quota(BaseModel):
    quota_restant: int
    quota_reinit_le: datetime.date | None
    plan: str
    role: str = "utilisateur"


# ---------------------------------------------------------------------
# Back-office d'ingestion
# ---------------------------------------------------------------------


class Probleme(BaseModel):
    niveau: Literal["bloquant", "avertissement"]
    message: str


class ArticleDepot(BaseModel):
    numero: str
    chemin: str
    contenu: str
    page_debut: int | None = None


class DepotSortie(BaseModel):
    """Un dépôt en attente, tel qu'il apparaît dans la liste."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nom_fichier: str
    sha256: str
    source_url: str
    sigle: str
    titre: str
    type: str
    version: str
    date_consolidation: datetime.date
    statut: Literal["en_attente", "valide", "rejete"]
    nb_pages: int | None
    nb_articles: int
    nb_bloquants: int
    cree_le: datetime.datetime
    texte_id: int | None = None


class EntreeDiff(BaseModel):
    """Un article du dépôt, situé par rapport au corpus en vigueur.

    `resume` et `portee` viennent du modèle et ne sont qu'un confort de
    lecture : `statut` est produit par une comparaison textuelle
    déterministe, à laquelle le modèle ne touche pas.
    """

    numero: str
    statut: Literal["ajoute", "modifie", "abroge", "inchange"]
    article_id: int | None = None
    ancien: str | None = None
    nouveau: str | None = None
    chemin: str = ""
    similarite: float = 0.0
    resume: str | None = None
    portee: Literal["majeure", "mineure"] | None = None


class DepotDetail(DepotSortie):
    """Le dépôt avec son découpage complet, pour relecture."""

    articles: list[ArticleDepot] = []
    problemes: list[Probleme] = []
    # Renseignée après appel de /analyser. Vide tant que le diff n'a pas
    # été demandé — on ne fait pas travailler le modèle sans intention.
    analyse: list[EntreeDiff] = []
    articles_retenus: list[str] = []


class RelectureEntree(BaseModel):
    """Les articles que le juriste déclare avoir relus."""

    numeros: list[str]


class RoleEntree(BaseModel):
    role: Literal["utilisateur", "juriste", "admin"]


class UtilisateurSortie(BaseModel):
    """Un compte, vu par l'administration.

    CE QUI EST EXPOSE, ET CE QUI NE L'EST PAS. L'administrateur voit
    l'identite du compte, son role, son forfait et sa consommation :
    c'est ce dont il a besoin pour attribuer un droit, constater un
    paiement ou repondre a une reclamation.

    Il ne voit NI les conversations, NI les favoris, NI les annotations
    personnelles. Ce sont des notes de travail sur des dossiers
    clients ; administrer le service ne donne aucune legitimite a les
    lire, et aucune route ne les expose.

    Le mot de passe n'apparait evidemment pas : il n'est de toute facon
    stocke que sous forme d'empreinte.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    prenom: str | None = None
    role: str
    plan: str
    quota_restant: int = 0
    plan_echeance: datetime.date | None = None
    # Le compte est-il rattache a Google ? Utile au diagnostic : un
    # compte Google n'a pas de mot de passe a reinitialiser.
    connexion_google: bool = False
    # Date d'acceptation des conditions. C'EST NOTRE MEILLEURE
    # APPROXIMATION DE LA DATE D'INSCRIPTION : la table ne porte pas de
    # `cree_le`. A ne pas presenter comme autre chose qu'elle est.
    cgu_acceptees_le: datetime.datetime | None = None


class RepartitionAdmin(BaseModel):
    """Les chiffres qui disent l'etat du service en un coup d'oeil."""

    comptes: int
    comptes_par_role: dict[str, int] = {}
    comptes_google: int = 0

    abonnes_payants: int = 0
    abonnes_par_forfait: dict[str, int] = {}
    # Revenu mensuel recurrent, en francs CFA : somme des prix des
    # forfaits payants ENCORE VALIDES. On ne compte pas les echus, qui
    # ne rapportent plus rien.
    revenu_mensuel_fcfa: int = 0
    demandes_en_attente: int = 0

    avis_nombre: int = 0
    avis_moyenne: float | None = None

    textes: int = 0
    articles: int = 0
    articles_vectorises: int = 0


# ---------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------


class QuestionEntree(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    conversation_id: int | None = None


class CitationSortie(BaseModel):
    """Une citation VALIDEE : son article_id existe dans le contexte."""

    article_id: int
    sigle: str
    numero: str
    chemin: str
    extrait: str
    pourquoi: str | None = None


class ReponseChat(BaseModel):
    reponse: str
    citations: list[CitationSortie] = []
    confiance: Confiance
    mise_en_garde: str | None = None
    # Explicite plutot que deduit : le frontend affiche un rendu sobre et
    # non alarmant pour un refus, qui est une fonctionnalite du produit.
    refus: bool = False
    # Vrai quand les articles sont rendus sans rédaction : le service de
    # synthèse est indisponible. Ce n'est ni un refus ni une erreur.
    sans_synthese: bool = False
    conversation_id: int | None = None
    # Identifiant du message enregistre : c'est lui que visent l'export
    # PDF et le signalement. Sans lui, le frontend ne peut designer la
    # reponse qu'il a sous les yeux.
    message_id: int | None = None


# ---------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------


class TexteSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sigle: str
    titre: str
    type: str
    version: str
    date_consolidation: datetime.date


class ArticleSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero: str
    chemin: str
    contenu: str
    date_entree_vigueur: datetime.date
    date_abrogation: datetime.date | None = None


class ArticleDetail(ArticleSortie):
    """Article complet, avec ses voisins pour la navigation."""

    texte: TexteSortie
    precedent_id: int | None = None
    suivant_id: int | None = None


class ResultatRecherche(BaseModel):
    """Recherche plein texte classique : gratuite, hors quota, sans LLM."""

    id: int
    sigle: str
    numero: str
    chemin: str
    extrait: str
    score: float


# ---------------------------------------------------------------------
# Historique
# ---------------------------------------------------------------------


class MessageSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    contenu: str
    cree_le: datetime.datetime
    # Une conversation reprise doit rester sourcee : sans ses citations,
    # une reponse relue perd exactement ce qui la rendait verifiable.
    citations: list[CitationSortie] = []


class ConversationSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titre: str | None
    cree_le: datetime.datetime


class ConversationDetail(ConversationSortie):
    messages: list[MessageSortie] = []


class SignalementEntree(BaseModel):
    """Une réponse contestée par l'utilisateur."""

    message_id: int
    motif: Literal[
        "article_faux",
        "article_perime",
        "hors_sujet",
        "reponse_incomplete",
        "autre",
    ]
    commentaire: str | None = Field(default=None, max_length=2000)


class ProvenanceSortie(BaseModel):
    """Une ligne de la table de provenance publiée.

    Elle porte de quoi remonter une réponse contestée à sa source : URL
    officielle, empreinte du fichier ingéré, version consolidée et nom du
    validateur qui en répond.
    """

    id: int
    sigle: str
    titre: str
    type: str
    version: str
    date_consolidation: datetime.date
    source_url: str | None = None
    source_sha256: str | None = None
    valide_par: str | None = None
    articles: int
    vectorises: int


class FaitMarquant(BaseModel):
    numero: str
    resume: str


class EntreeJournal(BaseModel):
    """Une publication du corpus, en langage clair."""

    depot_id: int
    sigle: str
    titre: str
    version: str
    date_consolidation: datetime.date
    publie_le: datetime.datetime | None = None
    nb_articles: int
    ajoutes: int
    modifies: int
    abroges: int
    faits_marquants: list[FaitMarquant] = []


class PointConformite(BaseModel):
    """Un point vérifié dans le document déposé.

    « a_verifier » est le repli de toute incertitude : annoncer conforme
    à tort donnerait à l'utilisateur une fausse sécurité, ce qui est le
    pire résultat possible pour cet outil.
    """

    repere: str
    libelle: str
    statut: Literal["conforme", "ecart", "a_verifier"]
    constat: str


class RapportConformite(BaseModel):
    """Le rapport rendu à l'utilisateur.

    Aucun indice global n'y figure : un pourcentage laisserait croire à
    une garantie que le produit refuse explicitement de donner (§3).
    """

    modele: str
    # L'article qui fonde la grille — cliquable côté frontend.
    article_id: int
    sigle: str
    numero: str
    version_corpus: str
    points: list[PointConformite] = []
    compte: dict[str, int] = {}


# ---------------------------------------------------------------------
# Calculateurs fiscaux
# ---------------------------------------------------------------------


class CalculEntree(BaseModel):
    """Saisie d'un calculateur.

    Le montant transite en CHAINE, pas en nombre flottant : un float
    JSON arrondit silencieusement, et un montant fiscal arrondi en
    silence est exactement ce qu'on refuse de produire. La conversion
    se fait en Decimal cote serveur.
    """

    montant: str = Field(min_length=1, max_length=24)
    # Le montant saisi est-il TTC ? Ne concerne que la TVA ; les autres
    # calculateurs l'ignorent.
    sur_ttc: bool = False
    # Taille de l'entreprise, pour la patente : le tarif en depend.
    # Ignore par les autres calculateurs.
    categorie: Literal["grande", "moyenne", "petite"] | None = None


class BaseLegaleCalcul(BaseModel):
    """L'article qui fonde une ligne du resultat, avec son extrait.

    Sans lui, le chiffre au-dessus n'est qu'un chiffre. C'est ce qui
    permet au professionnel de justifier son calcul (§14).
    """

    libelle: str
    valeur: str
    sigle: str
    numero: str
    chemin: str
    extrait: str


class LigneCalcul(BaseModel):
    libelle: str
    montant: str
    # Absente sur les lignes qui ne se fondent sur aucun article — une
    # base saisie par l'utilisateur, par exemple. Lui en attacher une
    # fabriquerait une reference.
    base_legale: BaseLegaleCalcul | None = None


class TotalCalcul(BaseModel):
    libelle: str
    montant: str


class ResultatCalcul(BaseModel):
    intitule: str
    lignes: list[LigneCalcul] = []
    resultat: TotalCalcul


class CalculateurDisponible(BaseModel):
    cle: str
    libelle: str
    description: str
    sigle: str
    numero_article: str
    # Dit si l'article qui fonde le bareme est reellement en corpus.
    # Une interface qui proposerait un calculateur sans base legale
    # enverrait l'utilisateur vers un refus apres saisie.
    disponible: bool
    indisponible_parce_que: str | None = None


# ---------------------------------------------------------------------
# Favoris, annotations, veille ciblee
# ---------------------------------------------------------------------


class FavoriEntree(BaseModel):
    """Annotation attachee a un favori. Facultative.

    Marquer sans commenter est le cas le plus frequent ; exiger une
    note ferait renoncer au favori.
    """

    note: str | None = Field(default=None, max_length=4000)


class FavoriSortie(BaseModel):
    article_id: int
    sigle: str
    numero: str
    chemin: str
    # Tronque cote serveur : une liste de favoris ne doit pas peser
    # plusieurs centaines de kilo-octets sur une connexion lente.
    apercu: str
    note: str | None = None
    cree_le: datetime.datetime
    modifie_le: datetime.datetime | None = None

    version_vue: str | None = None
    version_courante: str

    # Deux facons de vieillir, qui ne se confondent pas : le texte a ete
    # revise, ou CET article a ete abroge. La seconde est plus grave.
    texte_revise: bool = False
    article_abroge: bool = False


class AlerteVeille(BaseModel):
    """Un article suivi qui a bouge depuis sa mise en favori.

    On signale et on renvoie a l'article ; on ne resume pas ce qui a
    change. Affirmer « le taux est passe de X a Y » sans l'avoir
    verifie serait exactement ce que ce produit refuse de faire.
    """

    article_id: int
    sigle: str
    numero: str
    version_vue: str | None = None
    version_courante: str
    motif: Literal["texte_revise", "article_abroge"]


# ---------------------------------------------------------------------
# Generateur de documents types
# ---------------------------------------------------------------------


class ModeleDocument(BaseModel):
    cle: str
    libelle: str
    sigle: str
    numero: str


class ChampDocument(BaseModel):
    """Un champ du questionnaire, tire d'une mention obligatoire.

    `libelle_legal` est l'intitule NON REECRIT : il sert de point de
    comparaison mot pour mot avec le texte de l'article pendant la
    relecture.
    """

    cle: str
    repere: str
    question: str
    libelle_legal: str


class QuestionnaireSortie(BaseModel):
    cle: str
    libelle: str
    sigle: str
    numero: str
    version_corpus: str
    champs: list[ChampDocument] = []


class DocumentEntree(BaseModel):
    """Reponses saisies, et format voulu.

    Les reponses ne sont JAMAIS conservees : elles portent des noms, des
    adresses et des montants de clients. Elles servent a assembler le
    document, puis la requete se termine.
    """

    reponses: dict[str, str] = {}
    format: Literal["pdf", "docx"] = "pdf"


# ---------------------------------------------------------------------
# Profil et preferences
# ---------------------------------------------------------------------


class ProfilEntree(BaseModel):
    """Mise a jour du profil.

    LES DEUX CHAMPS SONT FACULTATIFS ET DISTINCTS DE « vide ». `None`
    signifie « ne touche pas a ce champ » ; une chaine vide, elle,
    efface le prenom. Sans cette distinction, une interface qui
    n'affiche que les preferences effacerait le prenom a chaque
    enregistrement.
    """

    prenom: str | None = Field(default=None, max_length=60)
    preferences: dict | None = None


class ProfilSortie(BaseModel):
    email: str
    prenom: str | None = None
    # Ou chercher l'avatar : la photo televersee si elle existe, sinon
    # celle du compte Google, sinon rien.
    photo_url: str | None = None
    # L'utilisateur a-t-il choisi sa propre photo ? L'interface en a
    # besoin pour proposer « revenir a la photo Google ».
    photo_televersee: bool = False
    photo_google: str | None = None
    # Deux lettres pour l'avatar quand la photo ne charge pas. Calculees
    # cote serveur : l'interface n'a pas a reimplementer la regle.
    initiales: str

    # Lecture seule : ce sont des decisions du service, pas des
    # preferences. Les exposer evite d'avoir a expliquer pourquoi le
    # champ ne s'enregistre pas.
    role: str
    plan: str
    quota_restant: int
    connexion_google: bool

    cgu_version: str | None = None
    cgu_acceptees_le: datetime.datetime | None = None

    preferences: dict = {}


# ---------------------------------------------------------------------
# Avis sur l'application
# ---------------------------------------------------------------------


class AvisEntree(BaseModel):
    """Avis depose par un utilisateur sur l'application.

    LA NOTE EST OBLIGATOIRE, LE COMMENTAIRE NON. Donner une note coute
    un clic ; ecrire coute du temps. Exiger les deux ferait renoncer
    ceux qui n'ont qu'une impression a livrer — c'est-a-dire la plupart.

    Les bornes sont posees ici ET en base : l'API refuse proprement, la
    contrainte SQL garantit qu'aucune autre voie d'ecriture ne puisse
    fausser la moyenne.
    """

    note: int = Field(ge=1, le=5)
    commentaire: str | None = Field(default=None, max_length=4000)


class AvisSortie(BaseModel):
    note: int
    commentaire: str | None = None
    cree_le: datetime.datetime
    modifie_le: datetime.datetime | None = None


class AvisAdministration(AvisSortie):
    """Un avis, vu par l'administration.

    L'AUTEUR EST IDENTIFIE ICI, ET NULLE PART AILLEURS. Repondre a un
    avis suppose de savoir de qui il vient ; en revanche rien de tout
    ceci n'est expose aux autres utilisateurs.
    """

    utilisateur_id: int
    email: str
    prenom: str | None = None


class SyntheseAvis(BaseModel):
    """Ce que l'administration voit d'un coup d'oeil.

    La moyenne seule trompe : 4,0 sur deux avis et 4,0 sur deux cents
    ne disent pas la meme chose. Le nombre l'accompagne toujours, et la
    repartition montre si la moyenne recouvre un consensus ou deux
    camps.
    """

    nombre: int
    moyenne: float | None = None
    repartition: dict[int, int] = {}
    avis: list[AvisAdministration] = []


# ---------------------------------------------------------------------
# Forfaits et abonnements
# ---------------------------------------------------------------------


class ForfaitSortie(BaseModel):
    """Un forfait du catalogue, tel que l'interface le presente.

    LE PRIX ET LES CREDITS VOYAGENT ENSEMBLE. Afficher l'un sans
    l'autre laisserait comparer des forfaits sans savoir ce qu'ils
    contiennent. La marge, elle, ne sort jamais d'ici : c'est une
    donnee interne.
    """

    code: str
    libelle: str
    prix_fcfa: int
    credits: int
    argumentaire: str
    atouts: list[str]


class AbonnementSortie(BaseModel):
    """L'abonnement du compte courant."""

    forfait: ForfaitSortie
    credits_restants: int
    echeance: datetime.date | None = None
    # Une demande en attente empeche d'en deposer une autre : l'interface
    # a besoin de le savoir pour afficher l'attente plutot qu'un bouton.
    demande_en_attente: str | None = None
    # CamPay est-il configure sur ce serveur ? Sans lui, l'interface doit
    # proposer le reglement hors ligne plutot qu'un bouton qui echouera.
    paiement_mobile: bool = False
    # Compte d'exploitation (juriste, administrateur) : il n'achete pas
    # de forfait et n'est pas soumis au quota. L'interface doit le dire
    # plutot que d'afficher des boutons qui repondront 409.
    personnel: bool = False


class DemandeAbonnementEntree(BaseModel):
    forfait: str


class DemandeAbonnementSortie(BaseModel):
    id: int
    utilisateur_id: int
    email: str
    prenom: str | None = None
    forfait_code: str
    statut: str
    demande_le: datetime.datetime
    traite_le: datetime.datetime | None = None
    reference: str | None = None
    motif_refus: str | None = None


class ValidationAbonnement(BaseModel):
    """Ce que l'administrateur constate en ouvrant les credits.

    LA REFERENCE DE PAIEMENT EST EXIGEE. Valider sans elle rendrait
    tout litige insoluble : plus rien ne relierait l'abonnement ouvert
    au paiement recu.
    """

    reference: str = Field(min_length=3, max_length=120)
    # Duree de validite, en mois. Un mois par defaut, parce que c'est ce
    # que le prix affiche represente.
    mois: int = Field(default=1, ge=1, le=12)


class RefusAbonnement(BaseModel):
    motif: str = Field(min_length=3, max_length=500)


class PaiementEntree(BaseModel):
    """Ce que le navigateur envoie pour lancer un paiement.

    LE MONTANT N'Y FIGURE PAS, ET C'EST VOULU. Il est lu dans le
    catalogue a partir du code de forfait, cote serveur. L'accepter
    depuis le navigateur reviendrait a laisser l'abonne choisir son
    prix.

    Le numero n'est pas un secret : c'est un identifiant. Le code
    Mobile Money, lui, est saisi par l'abonne sur son telephone et
    n'entre jamais dans l'application.
    """

    forfait: str
    telephone: str = Field(min_length=9, max_length=20)


class PaiementSortie(BaseModel):
    reference: str
    statut: str
    # Code a composer si l'invite USSD n'apparait pas d'elle-meme :
    # sans lui, l'abonne attend un ecran qui ne vient parfois pas.
    code_ussd: str | None = None
    operateur: str | None = None
    # Renseigne des que le paiement aboutit, pour que l'interface
    # affiche le nouveau forfait sans second appel.
    abonnement: AbonnementSortie | None = None
