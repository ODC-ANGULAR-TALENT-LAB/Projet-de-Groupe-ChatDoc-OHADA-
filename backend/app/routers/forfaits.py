"""Forfaits, abonnements et demandes de changement.

AUCUN SECRET DE PAIEMENT N'ENTRE ICI. Ni numero de carte, ni code
Mobile Money, ni identifiant bancaire. L'encaissement passe par CamPay,
dont le flux « collect » pousse une invite USSD sur le telephone de
l'abonne : il valide sur SON appareil, aupres de SON operateur. Nous
n'envoyons qu'un numero et un montant, et nous lisons un etat.

DEUX CHEMINS POUR PAYER, ET C'EST VOULU :

  - Mobile Money, immediat, quand CamPay est configure ;
  - especes ou virement, constates par un administrateur qui consigne
    la reference du paiement.

Le second n'est pas un vestige : un cabinet qui regle en especes ou par
virement ne doit pas se voir refuser l'abonnement faute de MoMo.

DEUX SENS, DEUX REGIMES. Monter en forfait engage un paiement.
Redescendre au gratuit n'engage personne : c'est immediat, et
l'utilisateur n'a d'accord a demander a quiconque.

CE QUI OUVRE UN ABONNEMENT, ET RIEN D'AUTRE : un SUCCESSFUL constate
par le serveur aupres de CamPay, un rappel dont la signature est
verifiee, ou la main d'un administrateur. Aucune route accessible a
l'utilisateur ne peut lui accorder des credits.
"""

from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import parametres
from app.db import get_db
from app.dependances import administrateur, utilisateur_courant
from app.models import Utilisateur
from app.schemas import (
    AbonnementSortie,
    DemandeAbonnementEntree,
    DemandeAbonnementSortie,
    ForfaitSortie,
    PaiementEntree,
    PaiementSortie,
    RefusAbonnement,
    ValidationAbonnement,
)
from app.services import campay
from app.services.forfaits import (
    PAR_CODE,
    catalogue_visible,
    credits_du_plan,
    forfait,
)

journal = logging.getLogger(__name__)

routeur = APIRouter(tags=["forfaits"])


def _en_sortie(f) -> ForfaitSortie:
    return ForfaitSortie(
        code=f.code,
        libelle=f.libelle,
        prix_fcfa=f.prix_fcfa,
        credits=f.credits,
        argumentaire=f.argumentaire,
        atouts=list(f.atouts),
    )


@routeur.get("/forfaits")
def catalogue() -> list[ForfaitSortie]:
    """Le catalogue, lisible sans compte.

    PUBLIC A DESSEIN : le prix est ce qu'on veut connaitre AVANT de
    s'inscrire. Le cacher derriere l'authentification obligerait a
    creer un compte pour savoir ce que coute le service.
    """
    return [_en_sortie(f) for f in catalogue_visible()]


@routeur.get("/moi/abonnement")
def mon_abonnement(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> AbonnementSortie:
    """Mon forfait, mes credits restants, et ma demande en cours."""
    en_attente = db.execute(
        text(
            "SELECT forfait_code FROM demande_abonnement "
            "WHERE utilisateur_id = :uid AND statut = 'en_attente'"
        ),
        {"uid": utilisateur.id},
    ).scalar()

    return AbonnementSortie(
        forfait=_en_sortie(forfait(utilisateur.plan)),
        credits_restants=utilisateur.quota_restant,
        echeance=utilisateur.plan_echeance,
        demande_en_attente=en_attente,
        paiement_mobile=parametres.campay_configure,
    )


@routeur.post("/moi/abonnement")
def demander_un_forfait(
    corps: DemandeAbonnementEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> AbonnementSortie:
    """Demande un changement de forfait.

    LA DESCENTE VERS LE GRATUIT EST IMMEDIATE. Elle ne coute rien a
    personne, et faire attendre quelqu'un qui renonce serait une facon
    de le retenir de force.

    LA MONTEE PASSE PAR UNE DEMANDE, parce qu'elle engage un paiement
    que l'application ne recoit pas. Les credits ne s'ouvrent qu'une
    fois ce paiement constate.
    """
    vise = PAR_CODE.get(corps.forfait)
    if vise is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Ce forfait n'existe pas."
        )

    if vise.code == utilisateur.plan:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "C'est déjà votre forfait actuel."
        )

    # Retour au gratuit : immediat, sans demande.
    if vise.prix_fcfa == 0:
        db.execute(
            text(
                "UPDATE demande_abonnement SET statut = 'refusee', "
                "motif_refus = 'Retour au forfait gratuit à la demande du compte.', "
                "traite_le = now() "
                "WHERE utilisateur_id = :uid AND statut = 'en_attente'"
            ),
            {"uid": utilisateur.id},
        )
        utilisateur.plan = "gratuit"
        utilisateur.plan_echeance = None
        # Les credits deja consommes le restent : on ne recharge pas au
        # plafond du gratuit, sinon renoncer a un forfait deviendrait un
        # moyen de se reapprovisionner.
        utilisateur.quota_restant = min(
            utilisateur.quota_restant, credits_du_plan("gratuit")
        )
        db.commit()
        return mon_abonnement(utilisateur, db)

    existante = db.execute(
        text(
            "SELECT forfait_code FROM demande_abonnement "
            "WHERE utilisateur_id = :uid AND statut = 'en_attente'"
        ),
        {"uid": utilisateur.id},
    ).scalar()
    if existante:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Une demande est déjà en attente. Annulez-la avant d'en faire une autre.",
        )

    db.execute(
        text(
            "INSERT INTO demande_abonnement (utilisateur_id, forfait_code) "
            "VALUES (:uid, :code)"
        ),
        {"uid": utilisateur.id, "code": vise.code},
    )
    db.commit()
    journal.info(
        "Demande d'abonnement %s deposee par le compte %s.", vise.code, utilisateur.id
    )
    return mon_abonnement(utilisateur, db)


@routeur.delete("/moi/abonnement/demande", status_code=status.HTTP_204_NO_CONTENT)
def annuler_ma_demande(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> None:
    """Retire une demande non encore traitee.

    Sans cela, quelqu'un qui se trompe de forfait resterait bloque
    jusqu'a ce qu'un administrateur veuille bien s'en occuper.
    """
    db.execute(
        text(
            "DELETE FROM demande_abonnement "
            "WHERE utilisateur_id = :uid AND statut = 'en_attente'"
        ),
        {"uid": utilisateur.id},
    )
    db.commit()


# ---------------------------------------------------------------------
# Paiement Mobile Money (CamPay)
#
# TROIS REGLES TIENNENT TOUTE CETTE SECTION :
#
# 1. Le MONTANT vient du catalogue, jamais du navigateur.
# 2. L'ACTIVATION n'a lieu que si CamPay, interroge par le serveur ou
#    signant son rappel, dit SUCCESSFUL. Rien de ce que le navigateur
#    affirme ne suffit.
# 3. L'ACTIVATION EST IDEMPOTENTE : le rappel signe et la verification
#    du navigateur peuvent arriver ensemble, et ne doivent pas ouvrir
#    deux mois d'abonnement.
# ---------------------------------------------------------------------


def _activer(db: Session, demande_id: int, reference_operateur: str | None) -> bool:
    """Ouvre l'abonnement si la demande est encore en attente.

    Rend True si l'activation a bien eu lieu, False si la demande avait
    deja ete traitee. C'EST CE TEST QUI REND L'OPERATION IDEMPOTENTE :
    il s'appuie sur le statut en base, pas sur ce que croit l'appelant.
    """
    ligne = db.execute(
        text(
            "SELECT utilisateur_id, forfait_code, statut, campay_reference "
            "FROM demande_abonnement WHERE id = :id FOR UPDATE"
        ),
        {"id": demande_id},
    ).mappings().first()

    if ligne is None or ligne["statut"] != "en_attente":
        return False

    vise = PAR_CODE.get(ligne["forfait_code"])
    compte = db.get(Utilisateur, ligne["utilisateur_id"])
    if vise is None or compte is None:
        return False

    aujourd_hui = datetime.date.today()
    compte.plan = vise.code
    compte.plan_echeance = aujourd_hui + datetime.timedelta(days=30)
    compte.quota_restant = vise.credits
    compte.quota_reinit_le = aujourd_hui

    db.execute(
        text(
            "UPDATE demande_abonnement SET statut = 'validee', traite_le = now(), "
            "paiement_statut = :etat, reference_operateur = :refop, "
            "reference = COALESCE(reference, :ref) WHERE id = :id"
        ),
        {
            "id": demande_id,
            "etat": campay.REUSSI,
            "refop": reference_operateur,
            "ref": ligne["campay_reference"],
        },
    )
    db.commit()
    journal.info(
        "Abonnement %s ouvert au compte %s par paiement mobile (%s).",
        vise.code,
        compte.id,
        ligne["campay_reference"],
    )
    return True


@routeur.post("/moi/abonnement/payer")
def payer_par_mobile(
    corps: PaiementEntree,
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> PaiementSortie:
    """Lance le paiement : une invite USSD part vers le telephone.

    L'ABONNE VALIDE SUR SON PROPRE APPAREIL, aupres de son operateur.
    Son code secret n'entre jamais dans cette application, qui n'envoie
    qu'un numero et un montant.

    Le montant est lu dans le catalogue a partir du seul code de
    forfait : le navigateur ne peut pas le proposer.
    """
    vise = PAR_CODE.get(corps.forfait)
    if vise is None or vise.prix_fcfa == 0:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Ce forfait payant n'existe pas."
        )

    if db.execute(
        text(
            "SELECT 1 FROM demande_abonnement "
            "WHERE utilisateur_id = :uid AND statut = 'en_attente'"
        ),
        {"uid": utilisateur.id},
    ).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Un paiement est déjà en cours. Terminez-le ou annulez-le.",
        )

    demande_id = db.execute(
        text(
            "INSERT INTO demande_abonnement (utilisateur_id, forfait_code) "
            "VALUES (:uid, :code) RETURNING id"
        ),
        {"uid": utilisateur.id, "code": vise.code},
    ).scalar()
    db.commit()

    try:
        collecte = campay.collecter(
            montant=vise.prix_fcfa,
            numero=corps.telephone,
            description=f"ChatDocs OHADA — forfait {vise.libelle}",
            reference_externe=f"abo-{demande_id}",
        )
    except (campay.PaiementRefuse, campay.PaiementIndisponible) as erreur:
        # La demande ne doit pas rester en attente sur un paiement qui
        # n'est jamais parti : elle bloquerait toute nouvelle tentative.
        db.execute(
            text("DELETE FROM demande_abonnement WHERE id = :id"), {"id": demande_id}
        )
        db.commit()
        code = (
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if isinstance(erreur, campay.PaiementRefuse)
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        raise HTTPException(code, str(erreur)) from erreur

    db.execute(
        text(
            "UPDATE demande_abonnement SET campay_reference = :ref, "
            "telephone = :tel, operateur = :op, paiement_statut = :etat "
            "WHERE id = :id"
        ),
        {
            "id": demande_id,
            "ref": collecte["reference"],
            "tel": collecte["numero"],
            "op": collecte["operateur"],
            "etat": campay.EN_ATTENTE,
        },
    )
    db.commit()

    return PaiementSortie(
        reference=collecte["reference"],
        statut=campay.EN_ATTENTE,
        code_ussd=collecte["code_ussd"],
        operateur=collecte["operateur"],
    )


@routeur.get("/moi/abonnement/paiement")
def suivre_mon_paiement(
    utilisateur: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
) -> PaiementSortie:
    """Ou en est le paiement en cours ?

    L'ETAT EST LU CHEZ CAMPAY, pas dans notre base : c'est la seule
    source qui fasse foi. Le navigateur appelle cette route pendant que
    l'abonne compose son code.
    """
    ligne = db.execute(
        text(
            "SELECT id, campay_reference FROM demande_abonnement "
            "WHERE utilisateur_id = :uid AND statut = 'en_attente' "
            "AND campay_reference IS NOT NULL"
        ),
        {"uid": utilisateur.id},
    ).mappings().first()

    if ligne is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Aucun paiement en cours."
        )

    try:
        etat = campay.etat(ligne["campay_reference"])
    except campay.PaiementIndisponible as erreur:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, str(erreur)
        ) from erreur

    if etat["statut"] == campay.REUSSI:
        _activer(db, ligne["id"], etat.get("reference_operateur"))
        db.refresh(utilisateur)
        return PaiementSortie(
            reference=etat["reference"],
            statut=campay.REUSSI,
            operateur=etat.get("operateur"),
            abonnement=mon_abonnement(utilisateur, db),
        )

    if etat["statut"] == campay.ECHOUE:
        db.execute(
            text(
                "UPDATE demande_abonnement SET statut = 'refusee', "
                "traite_le = now(), paiement_statut = :etat, "
                "motif_refus = 'Paiement non abouti côté opérateur.' "
                "WHERE id = :id"
            ),
            {"id": ligne["id"], "etat": campay.ECHOUE},
        )
        db.commit()

    return PaiementSortie(reference=etat["reference"], statut=etat["statut"])


@routeur.post("/paiements/campay", include_in_schema=False)
async def rappel_campay(requete: Request, db: Session = Depends(get_db)) -> dict:
    """Rappel signe de CamPay.

    CETTE URL EST PUBLIQUE PAR NATURE, donc traitee comme hostile. Sans
    verification de signature, il suffirait d'y poster un
    « SUCCESSFUL » pour s'offrir un abonnement. La signature est un JWT
    emis avec la cle du webhook ; faute de cle configuree, on refuse.

    On repond 200 meme quand la demande est introuvable : un rappel
    qu'on n'a pas su rattacher n'est pas une erreur de CamPay, et le
    faire echouer declencherait des reessais sans fin.
    """
    corps = dict(requete.query_params)
    if requete.headers.get("content-type", "").startswith("application/json"):
        try:
            corps.update(await requete.json())
        except ValueError:
            pass

    if not campay.signature_valide(corps.get("signature", "")):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Signature de rappel invalide."
        )

    reference = corps.get("reference")
    if not reference:
        return {"recu": True}

    ligne = db.execute(
        text(
            "SELECT id FROM demande_abonnement WHERE campay_reference = :ref"
        ),
        {"ref": reference},
    ).mappings().first()
    if ligne is None:
        journal.warning("Rappel CamPay sans demande correspondante : %s", reference)
        return {"recu": True}

    if corps.get("status") == campay.REUSSI:
        _activer(db, ligne["id"], corps.get("operator_reference"))
    elif corps.get("status") == campay.ECHOUE:
        db.execute(
            text(
                "UPDATE demande_abonnement SET statut = 'refusee', "
                "traite_le = now(), paiement_statut = :etat, "
                "motif_refus = 'Paiement non abouti côté opérateur.' "
                "WHERE id = :id AND statut = 'en_attente'"
            ),
            {"id": ligne["id"], "etat": campay.ECHOUE},
        )
        db.commit()

    return {"recu": True}


# ---------------------------------------------------------------------
# Administration
# ---------------------------------------------------------------------


@routeur.get("/admin/abonnements")
def demandes_a_traiter(
    _: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> list[DemandeAbonnementSortie]:
    """Les demandes, la plus ancienne d'abord.

    L'ORDRE N'EST PAS COSMETIQUE : quelqu'un qui a paye attend que ses
    credits s'ouvrent, et le faire passer apres un arrivant serait la
    pire facon de traiter le seul moment ou l'argent change de mains.
    """
    lignes = db.execute(
        text(
            """
            SELECT d.id, d.utilisateur_id, d.forfait_code, d.statut,
                   d.demande_le, d.traite_le, d.reference, d.motif_refus,
                   u.email, u.prenom
              FROM demande_abonnement d
              JOIN utilisateur u ON u.id = d.utilisateur_id
             ORDER BY d.statut = 'en_attente' DESC, d.demande_le ASC
             LIMIT 200
            """
        )
    ).mappings().all()
    return [DemandeAbonnementSortie(**ligne) for ligne in lignes]


@routeur.post("/admin/abonnements/{demande_id}/valider")
def valider_une_demande(
    demande_id: int,
    corps: ValidationAbonnement,
    patron: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> DemandeAbonnementSortie:
    """Ouvre les credits, le paiement ayant ete constate.

    C'EST ICI, ET NULLE PART AILLEURS, QUE LE FORFAIT S'OUVRE. Aucune
    route accessible a l'utilisateur ne peut lui accorder un forfait
    payant : sans cette separation, il suffirait d'appeler l'API pour
    s'offrir des credits.

    L'echeance part d'aujourd'hui et non de la date de demande : une
    demande traitee avec dix jours de retard ne doit pas amputer
    l'abonnement de dix jours.
    """
    demande = db.execute(
        text(
            "SELECT utilisateur_id, forfait_code, statut "
            "FROM demande_abonnement WHERE id = :id"
        ),
        {"id": demande_id},
    ).mappings().first()

    if demande is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demande introuvable.")
    if demande["statut"] != "en_attente":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cette demande a déjà été traitée."
        )

    vise = PAR_CODE.get(demande["forfait_code"])
    if vise is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Le forfait demandé n'existe plus au catalogue.",
        )

    compte = db.get(Utilisateur, demande["utilisateur_id"])
    if compte is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")

    aujourd_hui = datetime.date.today()
    # 30 jours par mois : une duree fixe, la meme pour tous, plutot
    # qu'un calcul calendaire ou fevrier vaudrait moins que mars.
    compte.plan = vise.code
    compte.plan_echeance = aujourd_hui + datetime.timedelta(days=30 * corps.mois)
    compte.quota_restant = vise.credits * corps.mois
    compte.quota_reinit_le = aujourd_hui

    db.execute(
        text(
            "UPDATE demande_abonnement SET statut = 'validee', traite_le = now(), "
            "traite_par = :par, reference = :ref WHERE id = :id"
        ),
        {"id": demande_id, "par": patron.id, "ref": corps.reference.strip()},
    )
    db.commit()
    journal.info(
        "Abonnement %s ouvert au compte %s jusqu'au %s (reference %s).",
        vise.code,
        compte.id,
        compte.plan_echeance,
        corps.reference.strip(),
    )
    return _demande(db, demande_id)


@routeur.post("/admin/abonnements/{demande_id}/refuser")
def refuser_une_demande(
    demande_id: int,
    corps: RefusAbonnement,
    patron: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> DemandeAbonnementSortie:
    """Refuse la demande, motif a l'appui.

    LE MOTIF EST OBLIGATOIRE. Un refus sans raison laisse quelqu'un qui
    croit avoir paye sans rien pour comprendre ni contester.
    """
    statut_actuel = db.execute(
        text("SELECT statut FROM demande_abonnement WHERE id = :id"),
        {"id": demande_id},
    ).scalar()
    if statut_actuel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demande introuvable.")
    if statut_actuel != "en_attente":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cette demande a déjà été traitée."
        )

    db.execute(
        text(
            "UPDATE demande_abonnement SET statut = 'refusee', traite_le = now(), "
            "traite_par = :par, motif_refus = :motif WHERE id = :id"
        ),
        {"id": demande_id, "par": patron.id, "motif": corps.motif.strip()},
    )
    db.commit()
    return _demande(db, demande_id)


def _demande(db: Session, demande_id: int) -> DemandeAbonnementSortie:
    ligne = db.execute(
        text(
            """
            SELECT d.id, d.utilisateur_id, d.forfait_code, d.statut,
                   d.demande_le, d.traite_le, d.reference, d.motif_refus,
                   u.email, u.prenom
              FROM demande_abonnement d
              JOIN utilisateur u ON u.id = d.utilisateur_id
             WHERE d.id = :id
            """
        ),
        {"id": demande_id},
    ).mappings().first()
    return DemandeAbonnementSortie(**ligne)
