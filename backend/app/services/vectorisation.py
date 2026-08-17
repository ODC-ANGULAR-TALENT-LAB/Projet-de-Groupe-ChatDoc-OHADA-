"""Generation des embeddings — l'implementation partagee.

COMME LE DECOUPAGE ET LES CONTROLES, CE MODULE EST LA SEULE
IMPLEMENTATION. La ligne de commande (ingestion/4_vectoriser.py) et le
back-office du juriste s'appuient dessus. Deux codes de vectorisation qui
divergeraient produiraient deux representations du meme article selon la
porte empruntee, et la recherche deviendrait incoherente sans que rien
ne le signale.

Le traitement est REPRENABLE par construction : on ne selectionne que
les articles dont l'embedding est encore nul. Une interruption ne perd
que le lot en cours.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import text

from app.config import parametres
from app.services.embeddings import calculer_embeddings, formater_vecteur

journal = logging.getLogger(__name__)

# Les fournisseurs plafonnent la taille d'une requete ; 64 tient
# largement sous la limite tout en amortissant les allers-retours.
TAILLE_LOT = 64


class VectorisationImpossible(RuntimeError):
    """Le fournisseur d'embeddings a echoue, ou repond hors format."""


def texte_a_vectoriser(article: dict) -> str:
    """Le contenu de l'article, precede de son adresse dans le texte.

    Le prefixe hierarchique ameliore nettement la pertinence : un article
    isole est souvent incomprehensible hors de son contexte.

    Les dispositions liminaires n'ont pas de chemin : on ne laisse pas
    de segment vide dans le prefixe, qui produirait "AUSCGIE >  >
    Article 1" et brouillerait la representation vectorielle.
    """
    adresse = [article["sigle"]]
    if article["chemin"]:
        adresse.append(article["chemin"])
    adresse.append(f"Article {article['numero']}")
    return " > ".join(adresse) + "\n" + article["contenu"]


def articles_a_traiter(
    cx, sigle: str | None = None, limite: int | None = None
) -> list[dict]:
    """Articles EN VIGUEUR dont l'embedding reste a calculer.

    Les articles clotures sont ecartes : ils restent consultables pour
    l'historique, mais la recherche ne doit pas les remonter, donc les
    vectoriser serait une depense pure.
    """
    conditions = ["a.embedding IS NULL", "a.date_abrogation IS NULL"]
    parametres_requete: dict = {}
    if sigle:
        conditions.append("t.sigle = :sigle")
        parametres_requete["sigle"] = sigle

    requete = (
        "SELECT a.id, a.numero, a.chemin, a.contenu, t.sigle "
        "FROM article a JOIN texte t ON t.id = a.texte_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY a.id"
    )
    if limite:
        requete += " LIMIT :limite"
        parametres_requete["limite"] = limite

    return [
        dict(ligne)
        for ligne in cx.execute(text(requete), parametres_requete).mappings()
    ]


def enregistrer_vecteurs(cx, couples: list[tuple[int, list[float]]]) -> None:
    """Ecrit les embeddings calcules.

    Seule colonne d'un article jamais reecrite par le pipeline : elle ne
    porte pas de contenu juridique, seulement sa representation.
    """
    cx.execute(
        text("UPDATE article SET embedding = CAST(:vecteur AS vector) WHERE id = :id"),
        [
            {"id": article_id, "vecteur": formater_vecteur(vecteur)}
            for article_id, vecteur in couples
        ],
    )


def creer_index(cx) -> None:
    """Index HNSW, a construire une fois TOUS les vecteurs en place."""
    cx.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_article_embedding ON article "
            "USING hnsw (embedding vector_cosine_ops)"
        )
    )


def vectoriser(
    moteur,
    sigle: str | None = None,
    limite: int | None = None,
    simuler: bool = False,
    progression=None,
) -> int:
    """Vectorise les articles en attente. Renvoie le nombre traite.

    `progression` est appele apres chaque lot avec (traites, total) :
    la ligne de commande s'en sert pour afficher son avancement, le
    back-office pour journaliser.
    """
    dimensions = parametres.embedding_dimensions

    with moteur.begin() as cx:
        articles = articles_a_traiter(cx, sigle, limite)

    if not articles:
        return 0

    traites = 0
    for debut in range(0, len(articles), TAILLE_LOT):
        lot = articles[debut : debut + TAILLE_LOT]
        textes = [texte_a_vectoriser(article) for article in lot]

        try:
            vecteurs = calculer_embeddings(textes, simuler=simuler)
        except (RuntimeError, httpx.HTTPError) as erreur:
            raise VectorisationImpossible(
                f"{erreur}\n{traites} article(s) deja enregistres : relancer "
                "reprendra ou le traitement s'est arrete."
            ) from erreur

        if vecteurs and len(vecteurs[0]) != dimensions:
            raise VectorisationImpossible(
                f"Le fournisseur renvoie des vecteurs de {len(vecteurs[0])} "
                f"dimensions, or la colonne embedding est declaree "
                f"VECTOR({dimensions}). Aligne EMBEDDING_DIMENSIONS et le "
                "schema SQL, puis revectorise tout."
            )

        with moteur.begin() as cx:
            enregistrer_vecteurs(
                cx, [(article["id"], v) for article, v in zip(lot, vecteurs)]
            )

        traites += len(lot)
        if progression:
            progression(traites, len(articles))

    return traites
