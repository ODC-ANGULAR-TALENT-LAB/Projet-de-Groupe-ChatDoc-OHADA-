"""Bibliotheque : textes, sommaire, lecture d'article, recherche.

Ces routes sont publiques et hors quota : consulter le corpus ne coute
rien et n'appelle aucun modele. C'est aussi ce qui permet a la
bibliotheque de rester consultable hors ligne (cache PWA) alors que le
chat exige la connexion.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Article, Depot, Texte
from app.schemas import (
    ArticleDetail,
    EntreeJournal,
    ProvenanceSortie,
    ResultatRecherche,
    TexteSortie,
)
from app.services.recherche import REQUETE_OU

routeur = APIRouter(tags=["corpus"])

LONGUEUR_EXTRAIT = 300


@routeur.get("/textes")
def lister_textes(db: Session = Depends(get_db)) -> list[TexteSortie]:
    textes = db.scalars(select(Texte).order_by(Texte.sigle)).all()
    return [TexteSortie.model_validate(t) for t in textes]


@routeur.get("/textes/{texte_id}/sommaire")
def sommaire(texte_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """Arborescence du texte, reconstruite depuis le champ chemin.

    Le sommaire ne bouge pas pendant une session : le frontend le met en
    cache et ne le redemande pas.
    """
    if db.get(Texte, texte_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Texte introuvable")

    articles = db.execute(
        select(Article.id, Article.numero, Article.chemin)
        .where(Article.texte_id == texte_id, Article.date_abrogation.is_(None))
        .order_by(Article.id)
    ).all()

    arbre: dict[str, list[dict]] = {}
    for identifiant, numero, chemin in articles:
        arbre.setdefault(chemin, []).append({"id": identifiant, "numero": numero})

    return [{"chemin": chemin, "articles": liste} for chemin, liste in arbre.items()]


@routeur.get("/articles/{article_id}")
def lire_article(article_id: int, db: Session = Depends(get_db)) -> ArticleDetail:
    """Article complet, avec ses voisins pour la navigation."""
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article introuvable")

    voisin = (
        lambda comparaison, ordre: db.scalar(
            select(Article.id)
            .where(
                Article.texte_id == article.texte_id,
                Article.date_abrogation.is_(None),
                comparaison,
            )
            .order_by(ordre)
            .limit(1)
        )
    )

    detail = ArticleDetail.model_validate(article)
    detail.texte = TexteSortie.model_validate(article.texte)
    detail.precedent_id = voisin(Article.id < article.id, Article.id.desc())
    detail.suivant_id = voisin(Article.id > article.id, Article.id.asc())
    return detail


@routeur.get("/recherche")
def recherche_plein_texte(
    q: str = Query(min_length=2, max_length=200),
    limite: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ResultatRecherche]:
    """Recherche plein texte classique, sans LLM : gratuite, hors quota."""
    requete = text(
        f"WITH requete AS (SELECT {REQUETE_OU} AS q) "
        "SELECT a.id, t.sigle, a.numero, a.chemin, a.contenu, "
        "ts_rank(a.recherche_fts, r.q) AS score "
        "FROM article a JOIN texte t ON t.id = a.texte_id, requete r "
        "WHERE a.date_abrogation IS NULL AND a.recherche_fts @@ r.q "
        "ORDER BY score DESC LIMIT :limite"
    )
    lignes = db.execute(requete, {"question": q, "limite": limite}).mappings()

    return [
        ResultatRecherche(
            id=ligne["id"],
            sigle=ligne["sigle"],
            numero=ligne["numero"],
            chemin=ligne["chemin"],
            extrait=ligne["contenu"][:LONGUEUR_EXTRAIT],
            score=float(ligne["score"]),
        )
        for ligne in lignes
    ]


@routeur.get("/provenance")
def table_de_provenance(db: Session = Depends(get_db)) -> list[ProvenanceSortie]:
    """La table de provenance, publiée (§2 ter).

    ELLE EST AUSSI LA PROTECTION DU PROJET. Le cahier des charges est
    explicite : « toute réponse contestée peut être remontée à sa source
    exacte ». Pour chaque texte : la source officielle, l'empreinte du
    fichier ingéré, la version consolidée et le nom du validateur.

    Publique et hors quota, comme le reste de la bibliothèque : une
    transparence qu'il faudrait un compte pour consulter n'en serait pas
    une.

    Le compte d'articles ne retient que ceux EN VIGUEUR : afficher les
    versions closes gonflerait le chiffre sans rien dire du corpus
    réellement interrogeable.
    """
    lignes = db.execute(
        text(
            "SELECT t.id, t.sigle, t.titre, t.type, t.version, "
            "       t.date_consolidation, t.source_url, t.source_sha256, "
            "       t.valide_par, "
            "       count(a.id) FILTER (WHERE a.date_abrogation IS NULL) AS articles, "
            "       count(a.embedding) FILTER (WHERE a.date_abrogation IS NULL) "
            "         AS vectorises "
            "FROM texte t LEFT JOIN article a ON a.texte_id = t.id "
            "GROUP BY t.id ORDER BY t.sigle, t.date_consolidation DESC"
        )
    ).mappings()
    return [ProvenanceSortie(**ligne) for ligne in lignes]


@routeur.get("/journal")
def journal_des_mises_a_jour(db: Session = Depends(get_db)) -> list[EntreeJournal]:
    """Ce qui a changé dans le corpus, en langage clair (§2 ter).

    Alimenté par l'historique des dépôts validés : chaque publication
    d'un texte y figure avec sa date, son validateur et le décompte des
    articles ajoutés, modifiés et abrogés — issu du diff produit à
    l'étape d'analyse.

    Un corpus qui change sans le dire vaut à peine mieux qu'un corpus
    périmé : l'utilisateur doit pouvoir constater qu'on l'entretient.
    """
    depots = db.scalars(
        select(Depot)
        .where(Depot.statut == "valide")
        .order_by(Depot.decide_le.desc())
        .limit(50)
    ).all()

    entrees = []
    for depot in depots:
        analyse = depot.analyse or []
        compte = {"ajoute": 0, "modifie": 0, "abroge": 0}
        for entree in analyse:
            if entree["statut"] in compte:
                compte[entree["statut"]] += 1

        # Les résumés produits par le modèle à l'analyse, repris tels
        # quels : ils ont été relus par le juriste avant validation.
        faits = [
            {"numero": e["numero"], "resume": e.get("resume") or ""}
            for e in analyse
            if e["statut"] == "modifie" and e.get("resume")
        ]

        entrees.append(
            EntreeJournal(
                depot_id=depot.id,
                sigle=depot.sigle,
                titre=depot.titre,
                version=depot.version,
                date_consolidation=depot.date_consolidation,
                publie_le=depot.decide_le,
                nb_articles=len(depot.articles),
                ajoutes=compte["ajoute"],
                modifies=compte["modifie"],
                abroges=compte["abroge"],
                faits_marquants=faits[:8],
            )
        )
    return entrees
