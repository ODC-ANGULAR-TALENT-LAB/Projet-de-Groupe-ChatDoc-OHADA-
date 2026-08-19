"""Avis des utilisateurs sur l'application.

CE QUE CETTE ROUTE MESURE, ET CE QU'ELLE NE MESURE PAS. L'avis porte
sur le produit dans son ensemble : est-il utile, agreable, digne de
confiance ? Il ne dit rien de la qualite d'une reponse particuliere.
Confondre les deux serait tentant — une note basse ressemble a une
plainte sur la derniere reponse lue — mais on ne saurait pas quoi
corriger. Un retour par reponse est un autre objet, rattache a la
question, aux articles cites et a la reponse produite.

UN SEUL AVIS PAR COMPTE, MODIFIABLE. Quelqu'un dont l'opinion change
doit pouvoir la corriger, pas en empiler une seconde. La contrainte
d'unicite vit en base ; ici on ecrit en UPSERT, comme pour les favoris.

L'AVIS N'EST PAS ANONYME POUR L'ADMINISTRATION, et il ne l'est pour
personne d'autre. Aucune route ne publie les avis aux utilisateurs :
afficher des commentaires nominatifs sur un outil de travail juridique
exposerait qui utilise le produit, ce que personne n'a accepte en le
deposant.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependances import administrateur, utilisateur_courant
from app.models import Utilisateur
from app.schemas import AvisEntree, AvisSortie, SyntheseAvis

journal = logging.getLogger(__name__)

routeur = APIRouter(tags=["avis"])


@routeur.get("/moi/avis")
def mon_avis(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> AvisSortie | None:
    """L'avis de l'utilisateur courant, ou `null` s'il n'en a pas donne.

    `null` plutot qu'un 404 : n'avoir pas encore donne son avis est
    l'etat normal, pas une erreur. L'interface s'en sert pour choisir
    entre « Donner mon avis » et « Modifier mon avis ».
    """
    ligne = db.execute(
        text(
            "SELECT note, commentaire, cree_le, modifie_le "
            "FROM avis WHERE utilisateur_id = :uid"
        ),
        {"uid": utilisateur.id},
    ).mappings().first()
    return AvisSortie(**ligne) if ligne else None


@routeur.put("/moi/avis")
def enregistrer_mon_avis(
    corps: AvisEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> AvisSortie:
    """Depose l'avis, ou remplace celui qui existe.

    UN SEUL VERBE POUR LES DEUX GESTES, comme pour les favoris :
    l'interface n'a pas a savoir si un avis existe deja avant d'agir.

    `modifie_le` ne se remplit qu'a la revision. Distinguer un avis
    donne une fois d'un avis reconsidere a une valeur : le second dit
    que la personne est revenue sur son jugement.
    """
    commentaire = (corps.commentaire or "").strip() or None

    db.execute(
        text(
            """
            INSERT INTO avis (utilisateur_id, note, commentaire)
            VALUES (:uid, :note, :commentaire)
            ON CONFLICT (utilisateur_id) DO UPDATE
               SET note = EXCLUDED.note,
                   commentaire = EXCLUDED.commentaire,
                   modifie_le = now()
            """
        ),
        {"uid": utilisateur.id, "note": corps.note, "commentaire": commentaire},
    )
    db.commit()

    return mon_avis(utilisateur, db)


@routeur.delete("/moi/avis", status_code=status.HTTP_204_NO_CONTENT)
def retirer_mon_avis(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> None:
    """Retire son avis.

    Deposer un avis doit rester revocable : sans cela, un commentaire
    ecrit sous le coup de l'agacement resterait attache au compte pour
    toujours.
    """
    db.execute(
        text("DELETE FROM avis WHERE utilisateur_id = :uid"),
        {"uid": utilisateur.id},
    )
    db.commit()


@routeur.get("/admin/avis")
def synthese_des_avis(
    _: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> SyntheseAvis:
    """Tous les avis, avec de quoi les lire sans se tromper.

    LA MOYENNE N'EST JAMAIS SERVIE SEULE. Elle est accompagnee du
    nombre d'avis et de leur repartition : 4,0 sur deux avis et 4,0 sur
    deux cents ne se pilotent pas pareil, et une moyenne de 3 peut
    recouvrir un consensus tiede comme deux camps opposes.
    """
    lignes = db.execute(
        text(
            """
            SELECT a.utilisateur_id, a.note, a.commentaire,
                   a.cree_le, a.modifie_le,
                   u.email, u.prenom
              FROM avis a
              JOIN utilisateur u ON u.id = a.utilisateur_id
             ORDER BY COALESCE(a.modifie_le, a.cree_le) DESC
            """
        )
    ).mappings().all()

    notes = [ligne["note"] for ligne in lignes]
    return SyntheseAvis(
        nombre=len(notes),
        moyenne=round(sum(notes) / len(notes), 2) if notes else None,
        repartition={n: notes.count(n) for n in range(1, 6)},
        avis=[dict(ligne) for ligne in lignes],
    )
