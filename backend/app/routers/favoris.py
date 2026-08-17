"""Favoris, annotations personnelles, et veille ciblee.

CE QUE LE CAHIER DES CHARGES DEMANDE (§5, « Should ») : « recherche
plein texte classique, favoris et annotations personnelles », et
« notification ciblee des utilisateurs ayant consulte ou mis en favori
un article modifie ».

LES DEUX NE FONT QU'UN. Un favori sans suite serait un signet ; ce qui
lui donne sa valeur ici, c'est qu'il permet de PREVENIR quelqu'un quand
le texte qu'il suit bouge. C'est la difference entre un outil qu'on
consulte et un outil qui travaille pour vous.

LE POINT DE COMPARAISON EST LA VERSION DU TEXTE. On enregistre, au
moment du marquage, la version du texte telle qu'elle etait
(`version_vue`). Une alerte se declenche quand la version courante en
differe. Sans ce repere, on ne pourrait dire que « quelque chose a
bouge » — ce qui n'aide personne.

LES ANNOTATIONS SONT PRIVEES. Elles appartiennent a leur auteur : rien
ne les expose a un autre utilisateur, et le juriste qui tient le corpus
n'y a pas acces davantage. Ce sont des notes de travail sur des dossiers
clients.
"""

from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependances import utilisateur_courant
from app.models import Utilisateur
from app.schemas import AlerteVeille, FavoriEntree, FavoriSortie

journal = logging.getLogger(__name__)

routeur = APIRouter(tags=["favoris"])

LONGUEUR_NOTE = 4000

# Les colonnes d'un favori, jointes a l'article et a son texte. Un
# favori sans son article n'est qu'un identifiant : l'interface a besoin
# du numero, du sigle et d'un apercu pour en faire une ligne lisible.
CHAMPS = """
    f.article_id, f.note, f.cree_le, f.modifie_le, f.version_vue,
    a.numero, a.chemin, a.contenu, a.date_abrogation,
    t.sigle, t.titre, t.version AS version_courante
"""

DEPUIS = """
    FROM favori f
    JOIN article a ON a.id = f.article_id
    JOIN texte t ON t.id = a.texte_id
"""


def _en_sortie(ligne) -> dict:
    """Met en forme un favori, apercu compris.

    L'APERCU EST TRONQUE ICI, PAS DANS L'INTERFACE. Renvoyer le contenu
    entier de chaque favori ferait des reponses de plusieurs centaines
    de kilo-octets pour une simple liste, sur une connexion qui n'est ni
    constante ni rapide.
    """
    contenu = ligne["contenu"] or ""
    return {
        "article_id": ligne["article_id"],
        "sigle": ligne["sigle"],
        "numero": ligne["numero"],
        "chemin": ligne["chemin"],
        "apercu": contenu[:300] + ("…" if len(contenu) > 300 else ""),
        "note": ligne["note"],
        "cree_le": ligne["cree_le"],
        "modifie_le": ligne["modifie_le"],
        "version_vue": ligne["version_vue"],
        "version_courante": ligne["version_courante"],
        # Deux facons dont un favori peut avoir vieilli, et elles ne se
        # confondent pas : le texte a ete revise, ou CET article a ete
        # abroge. La seconde est plus grave.
        "texte_revise": bool(
            ligne["version_vue"] and ligne["version_vue"] != ligne["version_courante"]
        ),
        "article_abroge": ligne["date_abrogation"] is not None,
    }


@routeur.get("/favoris")
def lister_favoris(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> list[FavoriSortie]:
    """Les favoris de l'utilisateur, du plus recent au plus ancien."""
    lignes = db.execute(
        text(
            f"SELECT {CHAMPS} {DEPUIS} "
            "WHERE f.utilisateur_id = :uid ORDER BY f.cree_le DESC"
        ),
        {"uid": utilisateur.id},
    ).mappings().all()
    return [_en_sortie(ligne) for ligne in lignes]


@routeur.get("/favoris/{article_id}")
def etat_du_favori(
    article_id: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> FavoriSortie | None:
    """Cet article est-il en favori, et avec quelle note ?

    Rend `null` plutot qu'un 404 : « pas en favori » est une reponse
    normale, pas une erreur, et l'interface s'en sert pour dessiner le
    bouton dans le bon etat.
    """
    ligne = db.execute(
        text(
            f"SELECT {CHAMPS} {DEPUIS} "
            "WHERE f.utilisateur_id = :uid AND f.article_id = :aid"
        ),
        {"uid": utilisateur.id, "aid": article_id},
    ).mappings().first()
    return _en_sortie(ligne) if ligne else None


@routeur.put("/favoris/{article_id}")
def enregistrer_favori(
    article_id: int,
    corps: FavoriEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> FavoriSortie:
    """Met l'article en favori, ou met a jour son annotation.

    UN SEUL VERBE POUR LES DEUX GESTES. Marquer et annoter sont la meme
    intention : « cet article compte pour moi, voici pourquoi ». Deux
    routes obligeraient l'interface a savoir laquelle appeler, donc a
    connaitre l'etat avant d'agir.
    """
    article = db.execute(
        text("SELECT id, texte_id FROM article WHERE id = :aid"),
        {"aid": article_id},
    ).mappings().first()
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article introuvable.")

    note = (corps.note or "").strip() or None
    if note and len(note) > LONGUEUR_NOTE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"L'annotation dépasse {LONGUEUR_NOTE} caractères.",
        )

    db.execute(
        text(
            """
            INSERT INTO favori (utilisateur_id, article_id, note, version_vue)
            VALUES (
                :uid, :aid, :note,
                (SELECT t.version FROM texte t
                  JOIN article a ON a.texte_id = t.id WHERE a.id = :aid)
            )
            ON CONFLICT (utilisateur_id, article_id) DO UPDATE
               SET note = EXCLUDED.note, modifie_le = now()
            """
        ),
        {"uid": utilisateur.id, "aid": article_id, "note": note},
    )
    db.commit()

    return etat_du_favori(article_id, utilisateur, db)


@routeur.delete("/favoris/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def retirer_favori(
    article_id: int,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> None:
    """Retire l'article des favoris, annotation comprise.

    L'ANNOTATION PART AVEC. La conserver « au cas ou » garderait une
    note de travail sur un dossier client alors que l'utilisateur vient
    de demander le contraire.
    """
    db.execute(
        text(
            "DELETE FROM favori WHERE utilisateur_id = :uid AND article_id = :aid"
        ),
        {"uid": utilisateur.id, "aid": article_id},
    )
    db.commit()


@routeur.get("/veille")
def alertes_de_veille(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> list[AlerteVeille]:
    """Les articles suivis qui ont bouge depuis leur mise en favori.

    C'EST LA NOTIFICATION CIBLEE DU CAHIER DES CHARGES. Elle ne
    s'adresse qu'a ceux que le changement concerne, et elle nomme
    l'article — pas « le corpus a ete mis a jour », qui n'apprend rien
    a personne.

    ON NE DIT PAS CE QUI A CHANGE DANS LE TEXTE. Le diff article par
    article existe (back-office, §5) mais il s'adresse au juriste qui
    valide un depot. Ici on signale, on renvoie a l'article, et
    l'utilisateur juge : affirmer « le taux est passe de X a Y » sans
    l'avoir verifie serait exactement le genre de resume que ce produit
    refuse de faire.
    """
    lignes = db.execute(
        text(
            f"""
            SELECT {CHAMPS} {DEPUIS}
            WHERE f.utilisateur_id = :uid
              AND (
                    a.date_abrogation IS NOT NULL
                 OR (f.version_vue IS NOT NULL
                     AND f.version_vue <> t.version)
              )
            ORDER BY f.cree_le DESC
            """
        ),
        {"uid": utilisateur.id},
    ).mappings().all()

    alertes = []
    for ligne in lignes:
        favori = _en_sortie(ligne)
        alertes.append(
            {
                "article_id": favori["article_id"],
                "sigle": favori["sigle"],
                "numero": favori["numero"],
                "version_vue": favori["version_vue"],
                "version_courante": favori["version_courante"],
                "motif": (
                    "article_abroge" if favori["article_abroge"] else "texte_revise"
                ),
            }
        )

    if alertes:
        journal.info(
            "Veille : %s alerte(s) pour %s.", len(alertes), utilisateur.email
        )
    return alertes
