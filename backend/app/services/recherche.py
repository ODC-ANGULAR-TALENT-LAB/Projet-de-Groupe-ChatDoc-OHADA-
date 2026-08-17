"""C - Recherche hybride.

Si la recherche ne remonte pas les bons articles, aucun modele de
langage au monde ne produira une bonne reponse : il repondra
brillamment a partir des mauvais textes. Tout le reste du produit
repose sur ce fichier.

Pourquoi hybride et pas seulement vectoriel. La recherche vectorielle
comprend le sens ("delai de convocation" trouve un article qui parle de
"quinze jours avant la reunion") mais elle est mauvaise sur les termes
exacts : un numero d'article, un taux, un sigle. La recherche lexicale
fait l'inverse. On combine les deux par fusion de rangs reciproques.

DEUX SCORES, DEUX ROLES - a ne pas confondre :

  score_rrf        sert a CLASSER. Il n'a pas d'echelle interpretable :
                   avec k=60 et deux listes, son maximum theorique vaut
                   2/61, soit environ 0,033.
  score_vectoriel  similarite cosinus, entre 0 et 1. C'est LUI qu'on
                   compare a SEUIL_PERTINENCE pour decider d'un refus.

Le guide compare SEUIL_PERTINENCE (0,55) au score renvoye en seconde
position du tuple, qui est le score RRF : ce test refuserait toutes les
questions, sans exception. D'ou la fonction pertinence() ci-dessous.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import text

from app.config import parametres
from app.db import moteur
from app.services.embeddings import calculer_embeddings, formater_vecteur

# Nombre de candidats demandes a CHACUNE des deux recherches avant
# fusion. Plus large que le nombre final : c'est la fusion qui tranche.
NB_CANDIDATS = 20

# Constante d'amortissement de la fusion RRF. 60 est la valeur de
# reference de la litterature ; elle attenue l'ecart entre les premiers
# rangs, ce qui evite qu'une seule des deux listes impose son ordre.
K_RRF = 60

journal = logging.getLogger(__name__)

CHAMPS = "a.id, a.numero, a.chemin, a.contenu, t.sigle"

# Requete lexicale : les lexemes relies par OU, non par ET.
#
# plainto_tsquery('french', "delai de convocation d'une AG de SARL") rend
# 'del' & 'convoc' & 'assemble' & 'general' & 'sarl' : TOUS les termes
# doivent figurer dans l'article. Or une vraie question contient toujours
# des mots absents du texte vise - "delai", "SARL" - donc la conjonction
# echoue et la moitie lexicale ne remonte rien. La recherche se degrade
# alors en pure recherche vectorielle, silencieusement.
#
# On remplace donc les & par des | et on laisse ts_rank faire son travail :
# les articles couvrant le plus de termes, et les plus rares, remontent.
REQUETE_OU = (
    "replace(plainto_tsquery('french', :question)::text, '&', '|')::tsquery"
)


def rechercher_vectoriel(cx, vecteur: list[float], sigle: str | None) -> list[dict]:
    """Recherche par similarite de sens (pgvector, distance cosinus)."""
    conditions = ["a.date_abrogation IS NULL", "a.embedding IS NOT NULL"]
    valeurs: dict = {"vecteur": formater_vecteur(vecteur), "limite": NB_CANDIDATS}
    if sigle:
        conditions.append("t.sigle = :sigle")
        valeurs["sigle"] = sigle

    requete = text(
        f"SELECT {CHAMPS}, "
        "1 - (a.embedding <=> CAST(:vecteur AS vector)) AS score_vectoriel "
        "FROM article a JOIN texte t ON t.id = a.texte_id "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY a.embedding <=> CAST(:vecteur AS vector) "
        "LIMIT :limite"
    )
    return [dict(ligne) for ligne in cx.execute(requete, valeurs).mappings()]


def rechercher_lexical(cx, question: str, sigle: str | None) -> list[dict]:
    """Recherche plein texte francaise (termes exacts)."""
    conditions = ["a.date_abrogation IS NULL", "a.recherche_fts @@ r.q"]
    valeurs: dict = {"question": question, "limite": NB_CANDIDATS}
    if sigle:
        conditions.append("t.sigle = :sigle")
        valeurs["sigle"] = sigle

    requete = text(
        f"WITH requete AS (SELECT {REQUETE_OU} AS q) "
        f"SELECT {CHAMPS}, ts_rank(a.recherche_fts, r.q) AS score_lexical "
        "FROM article a JOIN texte t ON t.id = a.texte_id, requete r "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY score_lexical DESC "
        "LIMIT :limite"
    )
    return [dict(ligne) for ligne in cx.execute(requete, valeurs).mappings()]


def fusion_rrf(
    liste_vect: list[dict], liste_lex: list[dict], k: int = K_RRF, n: int = 8
) -> list[tuple[dict, float]]:
    """Fusion par rang reciproque.

    On ne regarde que la POSITION de chaque article dans chaque liste,
    ce qui evite d'avoir a normaliser deux scores qui n'ont ni la meme
    echelle ni la meme signification.

    Les deux listes sont fusionnees champ par champ : un article present
    des deux cotes conserve son score vectoriel ET son score lexical.
    Ecraser une entree par l'autre - ce que fait un simple dictionnaire
    construit sur la concatenation des listes - perdrait justement le
    score qui sert ensuite a decider du refus.
    """
    scores: dict[int, float] = {}
    articles: dict[int, dict] = {}

    for liste in (liste_vect, liste_lex):
        for rang, article in enumerate(liste, 1):
            identifiant = article["id"]
            scores[identifiant] = scores.get(identifiant, 0.0) + 1.0 / (k + rang)
            articles.setdefault(identifiant, {}).update(article)

    for identifiant, article in articles.items():
        article.setdefault("score_vectoriel", 0.0)
        article.setdefault("score_lexical", 0.0)
        article["score_rrf"] = scores[identifiant]

    meilleurs = sorted(scores.items(), key=lambda couple: couple[1], reverse=True)[:n]
    return [(articles[identifiant], score) for identifiant, score in meilleurs]


def rechercher(
    question: str,
    n: int | None = None,
    sigle: str | None = None,
    simuler: bool = False,
) -> list[tuple[dict, float]]:
    """Les n articles les plus pertinents, du meilleur au moins bon.

    Renvoie des couples (article, score_rrf) : la forme attendue par le
    reste du projet. Chaque article porte aussi ses scores bruts.
    """
    return rechercher_detaille(question, n, sigle, simuler)[0]


def rechercher_detaille(
    question: str,
    n: int | None = None,
    sigle: str | None = None,
    simuler: bool = False,
) -> tuple[list[tuple[dict, float]], str]:
    """Comme rechercher(), mais dit AUSSI par quel mode la reponse est venue.

    Deux modes possibles :
      "hybride"      vectoriel + lexical, le fonctionnement nominal
      "lexical_seul" le fournisseur d'embeddings est indisponible

    Le mode remonte jusqu'a l'utilisateur. Une degradation silencieuse
    serait le pire des comportements : la recherche continuerait de
    rendre des resultats, moins bons, sans que personne le sache. C'est
    exactement la panne qu'on ne voit pas.
    """
    n = n or parametres.nb_articles_contexte
    question = question.strip()
    if not question:
        return [], "hybride"

    vecteur = None
    mode = "hybride"
    try:
        vecteur = calculer_embeddings([question], simuler=simuler)[0]
    except (RuntimeError, httpx.HTTPError) as erreur:
        # Sans embeddings, la moitie semantique est muette : on le dit,
        # on ne fait pas semblant.
        journal.warning("Embeddings indisponibles, recherche lexicale seule : %s",
                        erreur)
        mode = "lexical_seul"

    with moteur.connect() as cx:
        liste_vect = rechercher_vectoriel(cx, vecteur, sigle) if vecteur else []
        liste_lex = rechercher_lexical(cx, question, sigle)

    return fusion_rrf(liste_vect, liste_lex, n=n), mode


def pertinence(resultats: list[tuple[dict, float]]) -> float:
    """Score de pertinence du meilleur resultat, entre 0 et 1.

    C'est cette valeur - et non le score RRF - qui se compare a
    SEUIL_PERTINENCE pour decider d'un refus. Elle est interpretable :
    0,55 veut dire quelque chose sur une similarite cosinus, rien du
    tout sur un score de fusion de rangs.
    """
    if not resultats:
        return 0.0
    return max(article["score_vectoriel"] for article, _ in resultats)


def corpus_est_vectorise() -> bool:
    """Y a-t-il au moins un article vectorise ?

    Sans embeddings, la moitie vectorielle de la recherche ne remonte
    rien et le systeme se degrade silencieusement en simple recherche
    plein texte - exactement le genre de panne qu'on ne voit pas.
    """
    with moteur.connect() as cx:
        return bool(
            cx.execute(
                text("SELECT 1 FROM article WHERE embedding IS NOT NULL LIMIT 1")
            ).scalar()
        )
