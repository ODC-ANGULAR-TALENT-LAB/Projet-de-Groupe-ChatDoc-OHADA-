"""Variables d'environnement de l'application.

Un seul endroit lit le fichier .env ; tout le reste du code importe
`parametres`. Les valeurs par defaut correspondent a l'environnement
local Docker Compose, sauf pour les secrets qui restent vides tant
qu'ils ne sont pas fournis.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/ -> backend/ -> racine du monorepo, ou vit le fichier .env
RACINE = Path(__file__).resolve().parents[2]

# Valeurs d'exemple de .env.example. Un .env recopie tel quel les porte
# encore : elles doivent compter comme "non renseigne", sinon le produit
# croit disposer d'un fournisseur et echoue a l'appel.
VALEURS_EXEMPLE = {
    "votre_cle_ici",
    "nom_du_modele",
    "nom_du_modele_embeddings",
    "votre_client_id.apps.googleusercontent.com",
    "chaine_aleatoire_longue",
    "https://api.exemple.com/v1/embeddings",
    "https://api.exemple.com/v1/messages",
}


def _valeur_reelle(valeur: str) -> str:
    """La valeur, ou une chaine vide s'il s'agit d'un exemple."""
    propre = (valeur or "").strip()
    return "" if propre in VALEURS_EXEMPLE else propre


class Parametres(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RACINE / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base de donnees (port 5435 : voir docker-compose.yml)
    database_url: str = "postgresql://chatdocs:chatdocs_local@localhost:5435/chatdocs"

    # Fournisseur LLM (phase E) - la cle ne quitte jamais le serveur
    #
    # LE NOM DU MODELE N'EST PAS CODE EN DUR. Il vient du .env, au meme
    # titre que la cle : le depot ne designe donc aucun fournisseur, et
    # en changer ne demande pas de toucher au code. Vide par defaut, ce
    # qui fait simplement basculer le produit en mode sans synthese
    # plutot que d'echouer a l'appel.
    llm_api_key: str = ""
    llm_modele: str = ""

    # VERSION DES CONDITIONS GENERALES D'UTILISATION.
    #
    # Elle est enregistree sur chaque compte a l'inscription. La faire
    # evoluer ici ne suffit pas : changer les conditions oblige a
    # redemander leur acceptation aux comptes existants, sinon la
    # version enregistree ne correspond plus a ce qu'ils ont lu.
    version_cgu: str = "2026-08"
    llm_max_tokens: int = 4096
    # Niveau d'effort du modele : low, medium, high, xhigh, max.
    # "low" tient la cible des 10 secondes ; monter d'un cran ameliore
    # les questions multi-articles au prix de la latence.
    llm_effort: str = "low"
    url_fournisseur: str = ""

    # DIALECTE PARLE PAR LE FOURNISSEUR DE REDACTION.
    #
    # Deux familles d'API se partagent le marche et ne se ressemblent
    # en rien : ni la forme du corps, ni le nom des champs, ni le
    # format du flux. Le projet en a change une fois faute de credit,
    # et rien ne dit que cela n'arrivera plus.
    #
    # Le protocole est donc une VARIABLE, au meme titre que la cle :
    # basculer d'un fournisseur a l'autre se fait dans l'environnement
    # de l'hebergeur, sans toucher au code ni reveler dans le depot
    # quel fournisseur est en service.
    llm_protocole: str = "anthropic"

    # Origines autorisees par CORS (phase F puis H : restreindre au seul
    # domaine du frontend en production).
    origines_autorisees: str = "http://localhost:4200"

    # Passe a true sur l'hebergement : active HSTS et masque le
    # diagnostic detaille de /sante.
    production: bool = False

    # Fournisseur d'embeddings (phase B, hors ligne)
    embedding_url: str = ""
    embedding_modele: str = ""
    embedding_dimensions: int = 1536
    embedding_api_key: str = ""

    @property
    def cle_embeddings(self) -> str:
        """La cle dediee si elle est renseignee, sinon celle du LLM."""
        return _valeur_reelle(self.embedding_api_key) or _valeur_reelle(
            self.llm_api_key
        )

    @property
    def llm_configure(self) -> bool:
        """Y a-t-il un fournisseur de redaction utilisable ?

        Un .env recopie depuis .env.example porte des valeurs d'exemple.
        Les traiter comme des cles valides ferait echouer l'appel au
        fournisseur avec un message technique, la ou le produit peut
        simplement basculer en mode sans synthese.
        """
        return bool(_valeur_reelle(self.llm_api_key) and _valeur_reelle(self.llm_modele))

    @property
    def embeddings_configures(self) -> bool:
        return bool(
            _valeur_reelle(self.embedding_url)
            and _valeur_reelle(self.embedding_modele)
            and self.cle_embeddings
        )

    @property
    def liste_origines(self) -> list[str]:
        """Les origines CORS, normalisees.

        POURQUOI NORMALISER. Sur Render, cette variable n'est pas
        saisie a la main : elle est injectee par `fromService` depuis
        le service du frontend, et cette reference livre un NOM D'HOTE
        NU — `chatdocs-web.onrender.com`, sans schema.

        Or CORS compare des ORIGINES au sens strict : `Origin:
        https://chatdocs-web.onrender.com` ne correspond pas a
        `chatdocs-web.onrender.com`. Sans ce prefixage, le navigateur
        bloquerait chaque requete, et le diagnostic serait penible :
        la configuration semble juste, l'API repond en direct, et
        seule l'application echoue.

        Une barre finale produit le meme faux negatif, pour la meme
        raison. Les entrees vides — virgule en trop — sont ecartees.
        """
        origines = []
        for brute in self.origines_autorisees.split(","):
            origine = brute.strip().rstrip("/")
            if not origine:
                continue
            if "://" not in origine:
                origine = f"https://{origine}"
            origines.append(origine)
        return origines

    # Authentification (phase G)
    jwt_secret: str = "a_changer_imperativement"

    # DUREE DE SESSION : 12 heures, soit une journee de travail.
    #
    # Elle etait de 30 minutes, ce qui ne correspond pas a l'usage : on
    # lit un acte uniforme, on compare plusieurs articles, on redige. Une
    # coupure toutes les demi-heures tombait en plein travail.
    #
    # Le risque assume est celui d'un poste laisse ouvert. Il est
    # acceptable ici : l'application ne manipule ni paiement ni donnee
    # d'etat civil, et ce qu'un tiers verrait — le corpus, public par
    # nature — ne vaut pas la gene d'une reconnexion toutes les demi-
    # heures. Les notes personnelles sont la seule donnee privee, et le
    # bouton de deconnexion reste a portee sur chaque page.
    #
    # A revoir si le produit accueille un jour des donnees de dossier
    # client : ce serait un tout autre arbitrage.
    jwt_expiration_minutes: int = 720

    # Connexion Google. Seul le client ID est utilise : il sert a
    # verifier que le jeton nous est bien destine. Le code secret ne
    # servirait qu'au flux "code d'autorisation", hors perimetre ici.
    google_client_id: str = ""
    google_client_secret: str = ""

    # Pipeline RAG (phases C et E)
    # Le seuil sera calibre avec des donnees en phase C.
    seuil_pertinence: float = 0.55
    nb_articles_contexte: int = 8

    # COUT VARIABLE MOYEN D'UNE QUESTION, EN FRANCS CFA.
    #
    # C'est le seul chiffre dont depend le dimensionnement des forfaits.
    # Il est ici, et non code en dur dans le catalogue, parce qu'il
    # change avec le fournisseur et avec ses tarifs — pas avec le
    # produit.
    #
    # Comment il a ete obtenu, pour pouvoir etre refait :
    #   entree  ~2 500 jetons (8 articles de 584 caracteres en moyenne
    #           dans cette base, prompt systeme de 1046 caracteres,
    #           question, fil, schema de sortie impose) ;
    #   sortie  ~800 jetons en pratique, sur un plafond de 4 096 ;
    #   plus l'embedding de la question, negligeable.
    #
    # VERIFIEZ-LE CONTRE LA FACTURE REELLE DU FOURNISSEUR avant
    # d'ouvrir les paiements : la valeur par defaut est une estimation,
    # et toute la grille tarifaire en decoule. Une facture par question
    # deux fois plus elevee ferait tomber la marge de 55 % a 10 %.
    cout_question_fcfa: float = 25.0

    # --- CamPay : encaissement Mobile Money (MTN MoMo, Orange Money) ---
    #
    # CE QUE L'APPLICATION NE VOIT JAMAIS : le code secret du payeur. Le
    # flux « collect » de CamPay envoie une invite USSD sur le telephone
    # de l'abonne, qui valide sur SON appareil. Nous n'envoyons qu'un
    # numero de telephone et un montant, et nous recevons un etat. Aucun
    # secret de paiement ne transite ni n'est stocke ici.
    #
    # Les identifiants ci-dessous sont ceux de l'APPLICATION marchande,
    # pas ceux d'un utilisateur. Ils restent cote serveur.
    campay_username: str = ""
    campay_password: str = ""
    # Cle de signature des rappels (webhook). SANS ELLE, N'IMPORTE QUI
    # POUVANT ATTEINDRE L'URL DE RAPPEL S'OFFRE UN ABONNEMENT : il
    # suffirait d'envoyer un faux « SUCCESSFUL ». Le rappel est refuse
    # tant qu'elle n'est pas configuree.
    campay_webhook_cle: str = ""
    # "demo" tant que les tests ne sont pas termines : l'environnement de
    # demonstration ne debite personne.
    campay_environnement: str = "demo"

    @property
    def campay_url(self) -> str:
        return (
            "https://www.campay.net"
            if self.campay_environnement.lower() in {"prod", "production", "live"}
            else "https://demo.campay.net"
        )

    @property
    def campay_configure(self) -> bool:
        """Peut-on encaisser ?

        Sans identifiants, l'interface doit proposer le paiement hors
        ligne plutot que d'echouer au moment du clic.
        """
        return bool(
            _valeur_reelle(self.campay_username)
            and _valeur_reelle(self.campay_password)
        )


parametres = Parametres()
