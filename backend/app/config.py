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
        return [origine.strip() for origine in self.origines_autorisees.split(",")]

    # Authentification (phase G)
    jwt_secret: str = "a_changer_imperativement"
    jwt_expiration_minutes: int = 30

    # Connexion Google. Seul le client ID est utilise : il sert a
    # verifier que le jeton nous est bien destine. Le code secret ne
    # servirait qu'au flux "code d'autorisation", hors perimetre ici.
    google_client_id: str = ""
    google_client_secret: str = ""

    # Pipeline RAG (phases C et E)
    # Le seuil sera calibre avec des donnees en phase C.
    seuil_pertinence: float = 0.55
    nb_articles_contexte: int = 8


parametres = Parametres()
