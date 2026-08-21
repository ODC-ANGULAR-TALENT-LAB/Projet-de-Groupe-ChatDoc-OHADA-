"""Back-office d'ingestion du corpus — l'espace du juriste.

LE FLUX EST EN QUATRE TEMPS, ET C'EST DELIBERE.

1. Depot : le juriste televerse un PDF AVEC sa provenance. Le serveur
   extrait, decoupe, controle — et s'arrete la. Rien n'entre dans le
   corpus interrogeable.
2. Analyse : le serveur compare le depot au corpus DEJA EN VIGUEUR et
   classe chaque article — ajoute, modifie, abroge, inchange. Le modele
   resume ensuite, en langage clair, ce qui change dans les articles
   modifies. Il ne fait que resumer : le classement est textuel et
   deterministe (voir app/services/diff_corpus.py).
3. Relecture : le juriste declare avoir lu chaque article qui a bouge.
   Les articles inchanges ne lui sont pas soumis — c'est tout l'apport
   de l'etape 2 : trente articles a relire au lieu de quatre cents.
4. Validation : le texte devient interrogeable, et la version precedente
   de chaque article modifie est CLOTUREE, jamais ecrasee.

Un back-office « je depose, c'est en ligne » retournerait la promesse du
produit contre lui : le cahier des charges pose comme interdit absolu
d'ingerer un document sans verification d'origine ni de date.

Precision de vocabulaire : televerser un document alimente le CORPUS
interroge, jamais les poids du modele. Il n'y a aucun entrainement ici.
"""

from __future__ import annotations

import datetime
import json
import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import parametres
from app.db import get_db
from app.dependances import administrateur, redacteur_corpus
from app.models import Article, Depot, Texte, Utilisateur
from app.schemas import (
    ForfaitAdmin,
    ForfaitCreation,
    ForfaitEntree,
    RepartitionAdmin,
    SignalementSortie,
    SuspensionEntree,
    TraitementSignalement,
    ArticleDepot,
    DepotDetail,
    DepotSortie,
    EntreeDiff,
    Probleme,
    RelectureEntree,
    RoleEntree,
    UtilisateurSortie,
)
from app.services.analyse_depot import resumer_modifications
from app.services.forfaits import (
    ForfaitRefuse,
    forfait,
    oublier_le_cache,
    verifier,
)
from app.services.controles import BLOQUANT
from app.services.diff_corpus import a_relire, comparer
from app.services.ingestion import DepotRefuse, ingerer
from app.services.vectorisation import VectorisationImpossible, vectoriser

journal = logging.getLogger(__name__)

routeur = APIRouter(prefix="/admin", tags=["back-office"])

TYPES_ACCEPTES = ("acte_uniforme", "code")


def _compter_bloquants(problemes: list[dict]) -> int:
    return sum(1 for p in problemes if p.get("niveau") == BLOQUANT)


def _vers_sortie(depot: Depot) -> DepotSortie:
    return DepotSortie(
        id=depot.id,
        nom_fichier=depot.nom_fichier,
        sha256=depot.sha256,
        source_url=depot.source_url,
        sigle=depot.sigle,
        titre=depot.titre,
        type=depot.type,
        version=depot.version,
        date_consolidation=depot.date_consolidation,
        statut=depot.statut,
        nb_pages=depot.nb_pages,
        nb_articles=len(depot.articles),
        nb_bloquants=_compter_bloquants(depot.problemes),
        cree_le=depot.cree_le,
        texte_id=depot.texte_id,
    )


@routeur.post("/depots", status_code=status.HTTP_201_CREATED)
async def deposer(
    fichier: UploadFile = File(...),
    source_url: str = Form(..., min_length=8),
    sigle: str = Form(..., min_length=2, max_length=20),
    titre: str = Form(..., min_length=5),
    version: str = Form(..., min_length=1, max_length=50),
    date_consolidation: datetime.date = Form(...),
    type: str = Form("acte_uniforme"),
    page_debut: int = Form(1, ge=1),
    page_fin: int | None = Form(None),
    juriste: Utilisateur = Depends(redacteur_corpus),
    db: Session = Depends(get_db),
) -> DepotDetail:
    """Téléverse un texte officiel. Ne l'ajoute PAS au corpus.

    La provenance est obligatoire : sans URL officielle, version et date
    de consolidation, un document ne peut pas être remonté à sa source
    en cas de contestation — et c'est cette traçabilité qui protège le
    projet.
    """
    if type not in TYPES_ACCEPTES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Type inconnu. Valeurs acceptées : {', '.join(TYPES_ACCEPTES)}.",
        )

    contenu = await fichier.read()

    try:
        resultat = ingerer(contenu, page_debut=page_debut, page_fin=page_fin)
    except DepotRefuse as erreur:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erreur)) from erreur

    # Le SHA-256 identifie le contenu, pas le nom : un même fichier
    # redéposé sous un autre nom est reconnu.
    deja = db.scalar(
        select(Depot).where(Depot.sha256 == resultat.sha256, Depot.statut == "valide")
    )
    if deja is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ce fichier a déjà été validé le "
            f"{deja.decide_le:%d/%m/%Y} (dépôt {deja.id}).",
        )

    depot = Depot(
        depose_par=juriste.id,
        nom_fichier=fichier.filename or "sans-nom.pdf",
        sha256=resultat.sha256,
        source_url=source_url,
        sigle=sigle.upper(),
        titre=titre,
        type=type,
        version=version,
        date_consolidation=date_consolidation,
        statut="en_attente",
        articles=resultat.articles,
        problemes=resultat.problemes,
        nb_pages=resultat.nb_pages,
        extrait_par_ocr=resultat.extrait_par_ocr,
    )
    db.add(depot)
    db.commit()
    db.refresh(depot)

    journal.info(
        "Depot %s cree par %s : %s articles, %s bloquant(s).",
        depot.id,
        juriste.email,
        len(depot.articles),
        _compter_bloquants(depot.problemes),
    )
    return detail_depot(depot.id, juriste, db)


@routeur.get("/depots")
def lister_depots(
    statut: str | None = None,
    juriste: Utilisateur = Depends(redacteur_corpus),
    db: Session = Depends(get_db),
) -> list[DepotSortie]:
    requete = select(Depot).order_by(Depot.cree_le.desc())
    if statut:
        requete = requete.where(Depot.statut == statut)
    return [_vers_sortie(depot) for depot in db.scalars(requete).all()]


@routeur.get("/depots/{depot_id}")
def detail_depot(
    depot_id: int,
    juriste: Utilisateur = Depends(redacteur_corpus),
    db: Session = Depends(get_db),
) -> DepotDetail:
    """Le découpage complet, pour relecture avant validation.

    Les contrôles automatiques ne remplacent pas les yeux : ouvre une
    vingtaine d'articles au hasard et compare-les au PDF original.
    """
    depot = db.get(Depot, depot_id)
    if depot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dépôt introuvable")

    base = _vers_sortie(depot)
    return DepotDetail(
        **base.model_dump(),
        articles=[ArticleDepot(**article) for article in depot.articles],
        problemes=[Probleme(**probleme) for probleme in depot.problemes],
        analyse=[EntreeDiff(**entree) for entree in (depot.analyse or [])],
        articles_retenus=list(depot.articles_retenus or []),
    )


def _articles_en_vigueur(db: Session, sigle: str) -> list[dict]:
    """Les articles du corpus actuellement applicables pour ce sigle.

    On ecarte les articles deja clotures : comparer un depot a des
    versions abrogees ferait ressortir comme « modifie » ce qui l'avait
    deja ete lors d'une revision precedente.
    """
    lignes = db.execute(
        text(
            "SELECT a.id, a.numero, a.chemin, a.contenu "
            "FROM article a JOIN texte t ON t.id = a.texte_id "
            "WHERE t.sigle = :sigle AND a.date_abrogation IS NULL "
            "ORDER BY a.id"
        ),
        {"sigle": sigle},
    ).mappings()
    return [dict(ligne) for ligne in lignes]


@routeur.post("/depots/{depot_id}/analyser")
def analyser_depot(
    depot_id: int,
    juriste: Utilisateur = Depends(redacteur_corpus),
    db: Session = Depends(get_db),
) -> DepotDetail:
    """Situe le dépôt par rapport au corpus en vigueur.

    C'est l'étape qui rend une mise à jour tenable. Sans elle, le juriste
    reçoit quatre cents articles sans savoir lesquels ont bougé ; avec
    elle, il relit les trente que la révision touche réellement.

    Le classement est produit par une comparaison textuelle
    déterministe. Le modèle intervient ensuite, et uniquement pour
    résumer les articles modifiés : il n'a aucun pouvoir sur le
    classement, et son indisponibilité ne bloque rien.
    """
    depot = db.get(Depot, depot_id)
    if depot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dépôt introuvable")

    analyse = comparer(depot.articles, _articles_en_vigueur(db, depot.sigle))
    analyse = resumer_modifications(analyse)

    depot.analyse = analyse
    db.commit()
    db.refresh(depot)

    journal.info(
        "Depot %s analyse par %s : %s article(s) a relire sur %s.",
        depot.id,
        juriste.email,
        len(a_relire(analyse)),
        len(analyse),
    )
    return detail_depot(depot.id, juriste, db)


@routeur.post("/depots/{depot_id}/relu")
def marquer_relu(
    depot_id: int,
    corps: RelectureEntree,
    juriste: Utilisateur = Depends(redacteur_corpus),
    db: Session = Depends(get_db),
) -> DepotDetail:
    """Enregistre les articles que le juriste déclare avoir relus.

    La relecture est cumulative : on peut y revenir en plusieurs fois
    sans perdre ce qui a déjà été lu. Un texte de quatre cents articles
    ne se relit pas d'une traite.
    """
    depot = db.get(Depot, depot_id)
    if depot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dépôt introuvable")

    deja = set(depot.articles_retenus or [])
    depot.articles_retenus = sorted(deja | set(corps.numeros))
    db.commit()
    db.refresh(depot)
    return detail_depot(depot.id, juriste, db)


@routeur.post("/depots/{depot_id}/valider")
def valider_depot(
    depot_id: int,
    juriste: Utilisateur = Depends(redacteur_corpus),
    db: Session = Depends(get_db),
) -> DepotSortie:
    """Fait entrer le texte dans le corpus interrogeable.

    C'est le seul endroit du produit où un document devient citable. La
    validation engage l'administrateur : son adresse figure dans la
    colonne `valide_par` de la table de provenance.
    """
    depot = db.get(Depot, depot_id)
    if depot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dépôt introuvable")
    if depot.statut != "en_attente":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ce dépôt est déjà « {depot.statut} ».",
        )

    bloquants = _compter_bloquants(depot.problemes)
    if bloquants:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{bloquants} problème(s) bloquant(s) : corrige le découpage "
            "avant de valider. Un corpus mal découpé contamine toutes les "
            "réponses qui s'appuieront dessus.",
        )

    # LA RELECTURE EST UNE BARRIERE, PAS UNE FORMALITE. Quand une analyse
    # a été produite, aucun article ayant bougé ne peut entrer au corpus
    # sans qu'un juriste ait déclaré l'avoir lu. C'est ce qui distingue
    # une validation d'un simple clic : son nom part dans la table de
    # provenance, et c'est lui qui répondra d'une citation contestée.
    if depot.analyse:
        attendus = {entree["numero"] for entree in a_relire(depot.analyse)}
        relus = set(depot.articles_retenus or [])
        manquants = sorted(attendus - relus)
        if manquants:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{len(manquants)} article(s) modifié(s) n'ont pas été relus : "
                f"{', '.join(manquants[:10])}"
                + (" ..." if len(manquants) > 10 else "")
                + ". La validation engage votre signature.",
            )

    texte = Texte(
        sigle=depot.sigle,
        titre=depot.titre,
        type=depot.type,
        version=depot.version,
        date_consolidation=depot.date_consolidation,
        source_url=depot.source_url,
        source_sha256=depot.sha256,
        # Qui répond de cette ingestion.
        valide_par=juriste.email,
    )
    db.add(texte)
    db.flush()

    # recherche_fts est calculé par PostgreSQL : c'est lui qui connaît
    # la configuration 'french', pas Python.
    db.execute(
        text(
            "INSERT INTO article (texte_id, numero, chemin, contenu, "
            "                     date_entree_vigueur, recherche_fts) "
            "VALUES (:texte_id, :numero, :chemin, :contenu, :date_vigueur, "
            "        to_tsvector('french', :contenu))"
        ),
        [
            {
                "texte_id": texte.id,
                "numero": article["numero"],
                "chemin": article["chemin"],
                "contenu": article["contenu"],
                "date_vigueur": depot.date_consolidation,
            }
            for article in depot.articles
        ],
    )

    # AUCUN ARTICLE N'EST JAMAIS ECRASE. La version precedente du texte
    # est CLOTUREE a la date de consolidation du nouveau depot : ses
    # articles restent en base, consultables, mais sortent du champ des
    # articles en vigueur — donc de la recherche.
    #
    # C'est ce qui rend possible « quel etait le taux en 2024 ? », et ce
    # qui permet de revenir en arriere si une ingestion se revele
    # defectueuse. Un UPDATE sur le contenu rendrait les deux impossibles.
    clotures = db.execute(
        text(
            "UPDATE article SET date_abrogation = :date_fin "
            "WHERE date_abrogation IS NULL AND texte_id IN ("
            "    SELECT id FROM texte WHERE sigle = :sigle AND id <> :nouveau"
            ")"
        ),
        {
            "date_fin": depot.date_consolidation,
            "sigle": depot.sigle,
            "nouveau": texte.id,
        },
    ).rowcount

    depot.statut = "valide"
    depot.decide_le = datetime.datetime.now(datetime.timezone.utc)
    depot.decide_par = juriste.id
    depot.texte_id = texte.id
    db.commit()
    db.refresh(depot)

    journal.info(
        "Depot %s valide par %s -> texte %s (%s articles, %s ancien(s) clotures).",
        depot.id,
        juriste.email,
        texte.id,
        len(depot.articles),
        clotures,
    )
    return _vers_sortie(depot)


def _vectoriser_en_fond(sigle: str, email: str) -> None:
    """Tache de fond : vectorise ce qui manque pour un sigle.

    Elle ne traite que les articles a embedding nul. Une revision qui
    touche trente articles en recalcule trente, pas quatre cents — c'est
    tout l'interet de ne cloturer que ce qui change plutot que de tout
    reinserer.
    """
    from app.db import moteur

    try:
        traites = vectoriser(moteur, sigle=sigle)
        journal.info("Vectorisation %s terminee : %s article(s) [%s].",
                     sigle, traites, email)
    except VectorisationImpossible as erreur:
        # Journalise et s'arrete : le traitement est reprenable, un
        # nouvel appel repartira des articles restes sans vecteur.
        journal.error("Vectorisation %s interrompue : %s", sigle, erreur)


@routeur.post("/textes/{texte_id}/vectoriser", status_code=status.HTTP_202_ACCEPTED)
def lancer_vectorisation(
    texte_id: int,
    taches: BackgroundTasks,
    juriste: Utilisateur = Depends(redacteur_corpus),
    db: Session = Depends(get_db),
) -> dict:
    """Calcule les embeddings manquants du texte, en tâche de fond.

    Tant qu'un article n'est pas vectorisé, la recherche se dégrade
    silencieusement en simple plein texte : il remonte sur les mots mais
    pas sur le sens, et le seuil de refus perd son signal. C'est
    exactement le genre de panne qui ne se voit pas — d'où le compteur
    « vectorisés » affiché en permanence dans l'état du corpus.
    """
    texte_cible = db.get(Texte, texte_id)
    if texte_cible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Texte introuvable")

    restants = db.scalar(
        select(func.count(Article.id)).where(
            Article.texte_id == texte_id,
            Article.embedding.is_(None),
            Article.date_abrogation.is_(None),
        )
    )
    if not restants:
        return {"lance": False, "restants": 0,
                "message": "Tous les articles en vigueur sont déjà vectorisés."}

    taches.add_task(_vectoriser_en_fond, texte_cible.sigle, juriste.email)
    return {
        "lance": True,
        "restants": restants,
        "message": f"{restants} article(s) en cours de vectorisation. "
                   "Rafraîchis l'état du corpus dans quelques instants.",
    }


@routeur.get("/utilisateurs")
def lister_utilisateurs(
    admin: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> list[UtilisateurSortie]:
    """Réservé à l'administration de l'application, pas au juriste."""
    utilisateurs = db.scalars(select(Utilisateur).order_by(Utilisateur.id)).all()
    return [UtilisateurSortie.model_validate(u) for u in utilisateurs]


@routeur.patch("/utilisateurs/{utilisateur_id}/role")
def changer_role(
    utilisateur_id: int,
    corps: RoleEntree,
    admin: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> UtilisateurSortie:
    """Attribue un rôle. Réservé à l'administrateur de l'application.

    Un juriste valide des textes ; il ne distribue pas les droits. La
    séparation est volontaire : sans elle, quiconque obtient le droit de
    valider un texte peut se l'octroyer à d'autres, et la chaîne de
    responsabilité inscrite dans la table de provenance ne veut plus rien
    dire.
    """
    cible = db.get(Utilisateur, utilisateur_id)
    if cible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")

    # RETIRER LE DERNIER ROLE D'ADMINISTRATEUR FERME LA PORTE A CLEF DE
    # L'INTERIEUR — que ce soit le sien ou celui d'un autre. Le controle
    # ne portait que sur l'auto-retrogradation ; il vaut desormais pour
    # tout retrait, et s'appuie sur la meme regle que la suspension et
    # la suppression.
    if corps.role != "admin":
        _proteger_le_dernier_administrateur(db, cible, "retrograder")

    ancien = cible.role
    cible.role = corps.role
    db.commit()
    db.refresh(cible)

    journal.info(
        "Role de %s : %s -> %s (par %s).", cible.email, ancien, cible.role, admin.email
    )
    return UtilisateurSortie.model_validate(cible)


@routeur.post("/depots/{depot_id}/rejeter")
def rejeter_depot(
    depot_id: int,
    juriste: Utilisateur = Depends(redacteur_corpus),
    db: Session = Depends(get_db),
) -> DepotSortie:
    """Écarte un dépôt. Le découpage est conservé comme trace."""
    depot = db.get(Depot, depot_id)
    if depot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dépôt introuvable")
    if depot.statut == "valide":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ce dépôt est déjà dans le corpus. Un texte validé ne se "
            "rejette pas : il s'abroge, en clôturant ses articles.",
        )

    depot.statut = "rejete"
    depot.decide_le = datetime.datetime.now(datetime.timezone.utc)
    depot.decide_par = juriste.id
    db.commit()
    db.refresh(depot)
    return _vers_sortie(depot)


@routeur.get("/corpus/etat")
def etat_corpus(
    juriste: Utilisateur = Depends(redacteur_corpus),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Ce que contient le corpus, et ce qui reste à vectoriser.

    Un texte chargé mais non vectorisé ne remonte que par la recherche
    lexicale : la moitié vectorielle est muette, sans que rien ne le
    signale côté utilisateur.
    """
    lignes = db.execute(
        text(
            "SELECT t.id, t.sigle, t.version, t.date_consolidation, "
            "       t.valide_par, count(a.id) AS articles, "
            "       count(a.embedding) AS vectorises "
            "FROM texte t LEFT JOIN article a ON a.texte_id = t.id "
            "GROUP BY t.id ORDER BY t.sigle"
        )
    ).mappings()

    return [
        {
            "id": ligne["id"],
            "sigle": ligne["sigle"],
            "version": ligne["version"],
            "date_consolidation": ligne["date_consolidation"],
            "valide_par": ligne["valide_par"],
            "articles": ligne["articles"],
            "vectorises": ligne["vectorises"],
            "pret": ligne["articles"] > 0 and ligne["articles"] == ligne["vectorises"],
        }
        for ligne in lignes
    ]


# Le routeur porte deja prefix="/admin" : ecrire "/admin/..."
# ici produirait /admin/admin/... — la route repondrait 404 sans
# que rien ne le signale, puisqu'elle EXISTE, ailleurs.
@routeur.get("/tableau-de-bord")
def tableau_de_bord(
    _: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> RepartitionAdmin:
    """Les chiffres qui disent l'etat du service en un coup d'oeil.

    POURQUOI UNE ROUTE ET NON SIX APPELS. L'interface d'administration
    ouvrait autrement six requetes pour dessiner un en-tete, et les
    chiffres arrivaient les uns apres les autres, dans le desordre. Ici
    ils sont pris au meme instant : ils se rapportent donc au meme etat,
    ce qui n'est pas un detail quand on compare des abonnes a un revenu.

    LE REVENU NE COMPTE QUE LES ABONNEMENTS ENCORE VALIDES. Additionner
    les forfaits echus gonflerait un chiffre dont on se sert pour
    decider : mieux vaut un revenu exact et modeste qu'un revenu flatteur
    et faux.
    """
    aujourd_hui = datetime.date.today()

    roles = dict(
        db.execute(
            text("SELECT role, count(*) FROM utilisateur GROUP BY role")
        ).all()
    )

    # LE PERSONNEL EST EXCLU DES CHIFFRES CLIENTS. Un juriste ou un
    # administrateur n'achete pas de forfait : les compter parmi les
    # abonnes gonflerait le nombre d'abonnes et le chiffre d'affaires
    # d'une vente qui n'a jamais eu lieu.
    #
    # LE GRATUIT EST UN FORFAIT COMME UN AUTRE dans la repartition :
    # quelqu'un qui n'a rien souscrit EST abonne a Decouverte, ce n'est
    # pas une absence d'abonnement. L'exclure laissait une colonne vide
    # la ou se trouve le gros des comptes, et rendait la repartition
    # illisible.
    repartition = db.execute(
        text(
            "SELECT plan, count(*) FROM utilisateur "
            "WHERE role = 'utilisateur' "
            "  AND (plan = 'gratuit' "
            "       OR plan_echeance IS NULL OR plan_echeance >= :jour) "
            "GROUP BY plan"
        ),
        {"jour": aujourd_hui},
    ).all()
    par_forfait = {plan: n for plan, n in repartition}

    # Le revenu, lui, ne compte QUE le payant et le non echu : le
    # gratuit ne rapporte rien, et un abonnement expire non plus.
    revenu = sum(
        forfait(plan).prix_fcfa * n
        for plan, n in repartition
        if forfait(plan).prix_fcfa > 0
    )

    notes = db.execute(text("SELECT note FROM avis")).scalars().all()
    corpus = db.execute(
        text(
            "SELECT (SELECT count(*) FROM texte) AS textes, "
            "       (SELECT count(*) FROM article) AS articles, "
            "       (SELECT count(embedding) FROM article) AS vectorises"
        )
    ).mappings().first()

    return RepartitionAdmin(
        # `comptes` compte TOUT LE MONDE, personnel compris : c'est le
        # nombre de comptes de l'application. `comptes_par_role` permet
        # de distinguer clients et exploitants, plutot que de masquer
        # les seconds dans un total qu'on ne pourrait plus recouper.
        comptes=sum(roles.values()),
        comptes_par_role=roles,
        comptes_google=db.execute(
            text("SELECT count(*) FROM utilisateur WHERE google_sub IS NOT NULL")
        ).scalar()
        or 0,
        # « Abonnes payants » garde son sens strict : ceux qui paient.
        abonnes_payants=sum(
            n for plan, n in par_forfait.items() if forfait(plan).prix_fcfa > 0
        ),
        abonnes_par_forfait=par_forfait,
        revenu_mensuel_fcfa=revenu,
        demandes_en_attente=db.execute(
            text(
                "SELECT count(*) FROM demande_abonnement WHERE statut = 'en_attente'"
            )
        ).scalar()
        or 0,
        avis_nombre=len(notes),
        avis_moyenne=round(sum(notes) / len(notes), 2) if notes else None,
        textes=corpus["textes"],
        articles=corpus["articles"],
        articles_vectorises=corpus["vectorises"],
    )


# ---------------------------------------------------------------------
# Catalogue des forfaits
#
# LA MARGE SE VERIFIE A L'ECRITURE, et c'est le prix a payer pour avoir
# sorti le catalogue du code. Tant qu'il y vivait, un test refusait
# toute grille sous le plancher ; une table modifiable depuis une
# console ne passe par aucun test. La verification s'appuie donc sur le
# SEUL chemin qui mene a la table : ces deux routes.
# ---------------------------------------------------------------------


def _forfaits_admin(db: Session) -> list[ForfaitAdmin]:
    lignes = db.execute(
        text(
            "SELECT f.code, f.libelle, f.prix_fcfa, f.credits, f.argumentaire, "
            "       f.atouts, f.essai, f.actif, f.ordre, "
            "       (SELECT count(*) FROM utilisateur u WHERE u.plan = f.code "
            "          AND u.role = 'utilisateur') AS abonnes "
            "  FROM forfait f ORDER BY f.ordre, f.code"
        )
    ).mappings().all()

    sorties = []
    for ligne in lignes:
        cout = ligne["credits"] * parametres.cout_question_fcfa
        marge = (
            None
            if ligne["prix_fcfa"] == 0
            else (ligne["prix_fcfa"] - cout) / ligne["prix_fcfa"]
        )
        sorties.append(
            ForfaitAdmin(
                code=ligne["code"],
                libelle=ligne["libelle"],
                prix_fcfa=ligne["prix_fcfa"],
                credits=ligne["credits"],
                argumentaire=ligne["argumentaire"] or "",
                atouts=list(ligne["atouts"] or []),
                essai=ligne["essai"],
                actif=ligne["actif"],
                ordre=ligne["ordre"],
                cout_variable_fcfa=round(cout, 2),
                marge=None if marge is None else round(marge, 4),
                abonnes=ligne["abonnes"],
            )
        )
    return sorties


@routeur.get("/forfaits")
def catalogue_administration(
    _: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> list[ForfaitAdmin]:
    """Le catalogue avec son economie et ses abonnes.

    Les forfaits INACTIFS figurent ici, contrairement au catalogue
    public : on doit pouvoir en reactiver un, et voir combien de
    comptes y sont encore rattaches.
    """
    return _forfaits_admin(db)


@routeur.post("/forfaits", status_code=status.HTTP_201_CREATED)
def creer_forfait(
    corps: ForfaitCreation,
    admin: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> ForfaitAdmin:
    """Ajoute un forfait au catalogue."""
    if db.execute(
        text("SELECT 1 FROM forfait WHERE code = :c"), {"c": corps.code}
    ).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Le code « {corps.code} » existe déjà."
        )

    try:
        verifier(corps.prix_fcfa, corps.credits, corps.essai)
    except ForfaitRefuse as erreur:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(erreur)
        ) from erreur

    db.execute(
        text(
            "INSERT INTO forfait (code, libelle, prix_fcfa, credits, "
            "  argumentaire, atouts, essai, actif, ordre, modifie_le, modifie_par) "
            "VALUES (:code, :libelle, :prix, :credits, :arg, "
            "  CAST(:atouts AS jsonb), :essai, :actif, :ordre, now(), :par)"
        ),
        {
            "code": corps.code,
            "libelle": corps.libelle.strip(),
            "prix": corps.prix_fcfa,
            "credits": corps.credits,
            "arg": corps.argumentaire.strip(),
            "atouts": json.dumps([a.strip() for a in corps.atouts if a.strip()]),
            "essai": corps.essai,
            "actif": corps.actif,
            "ordre": corps.ordre,
            "par": admin.id,
        },
    )
    db.commit()
    oublier_le_cache()
    journal.info("Forfait %s cree par le compte %s.", corps.code, admin.id)

    return next(f for f in _forfaits_admin(db) if f.code == corps.code)


@routeur.put("/forfaits/{code}")
def modifier_forfait(
    code: str,
    corps: ForfaitEntree,
    admin: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> ForfaitAdmin:
    """Modifie un forfait existant.

    LE CODE N'EST PAS MODIFIABLE : il est inscrit sur chaque compte
    abonne, et le changer les ferait tous retomber sur « forfait
    inconnu ». Pour renommer, on cree un forfait et on desactive
    l'ancien.

    DESACTIVER PLUTOT QUE SUPPRIMER, pour la meme raison : la ligne
    doit survivre aux comptes qui s'y rattachent encore.
    """
    if not db.execute(
        text("SELECT 1 FROM forfait WHERE code = :c"), {"c": code}
    ).first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Forfait introuvable.")

    # Le forfait gratuit ne se desactive pas : c'est celui sur lequel
    # tout compte retombe, a l'inscription comme a l'echeance d'un
    # abonnement. Sans lui, une inscription n'aurait plus de plan.
    if code == "gratuit" and not corps.actif:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Le forfait gratuit ne peut pas être désactivé : c'est celui sur "
            "lequel tout compte retombe à l'inscription et à l'échéance.",
        )

    try:
        verifier(corps.prix_fcfa, corps.credits, corps.essai)
    except ForfaitRefuse as erreur:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(erreur)
        ) from erreur

    db.execute(
        text(
            "UPDATE forfait SET libelle = :libelle, prix_fcfa = :prix, "
            "  credits = :credits, argumentaire = :arg, "
            "  atouts = CAST(:atouts AS jsonb), essai = :essai, "
            "  actif = :actif, ordre = :ordre, modifie_le = now(), "
            "  modifie_par = :par WHERE code = :code"
        ),
        {
            "code": code,
            "libelle": corps.libelle.strip(),
            "prix": corps.prix_fcfa,
            "credits": corps.credits,
            "arg": corps.argumentaire.strip(),
            "atouts": json.dumps([a.strip() for a in corps.atouts if a.strip()]),
            "essai": corps.essai,
            "actif": corps.actif,
            "ordre": corps.ordre,
            "par": admin.id,
        },
    )
    db.commit()
    oublier_le_cache()
    journal.info("Forfait %s modifie par le compte %s.", code, admin.id)

    return next(f for f in _forfaits_admin(db) if f.code == code)


# ---------------------------------------------------------------------
# Registre des signalements
# ---------------------------------------------------------------------


@routeur.get("/signalements")
def lister_signalements(
    _: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> list[SignalementSortie]:
    """Les reponses contestees, les ouvertes d'abord.

    LE REGISTRE EXISTAIT MAIS N'ETAIT PAS LISIBLE : une route permettait
    d'y ecrire, aucune de le consulter. Un registre qu'on ne lit pas ne
    protege de rien — et c'est precisement son role (§16 ter).

    La question et la reponse mise en cause accompagnent chaque ligne :
    trancher une contestation suppose de les relire, et aller les
    chercher ailleurs decouragerait de le faire.
    """
    lignes = db.execute(
        text(
            """
            SELECT s.id, s.message_id, s.motif, s.commentaire, s.statut,
                   s.correction, s.cree_le, s.traite_le,
                   u.email,
                   -- La table message stocke UN TOUR par ligne, pas une
                   -- paire : le signalement vise la reponse, et la
                   -- question est le tour utilisateur qui la precede
                   -- dans la meme conversation.
                   m.contenu AS reponse,
                   (SELECT q.contenu
                      FROM message q
                     WHERE q.conversation_id = m.conversation_id
                       AND q.role <> m.role
                       AND q.id < m.id
                     ORDER BY q.id DESC
                     LIMIT 1) AS question
              FROM signalement s
              LEFT JOIN utilisateur u ON u.id = s.utilisateur_id
              LEFT JOIN message m ON m.id = s.message_id
             ORDER BY s.statut = 'ouvert' DESC, s.cree_le DESC
             LIMIT 200
            """
        )
    ).mappings().all()
    return [SignalementSortie(**ligne) for ligne in lignes]


@routeur.post("/signalements/{signalement_id}/traiter")
def traiter_signalement(
    signalement_id: int,
    corps: TraitementSignalement,
    admin_courant: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> SignalementSortie:
    """Clot un signalement, en disant ce qui a ete fait.

    LA CORRECTION EST OBLIGATOIRE. Clore sans motif viderait le
    registre de sa valeur probante le jour ou il faudrait s'en servir :
    « traite » ne dit ni ce qui a ete constate, ni ce qui a ete corrige.
    """
    statut_actuel = db.execute(
        text("SELECT statut FROM signalement WHERE id = :id"), {"id": signalement_id}
    ).scalar()
    if statut_actuel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Signalement introuvable.")
    if statut_actuel != "ouvert":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ce signalement a déjà été traité."
        )

    db.execute(
        text(
            "UPDATE signalement SET statut = :statut, correction = :correction, "
            "traite_le = now(), traite_par = :par WHERE id = :id"
        ),
        {
            "id": signalement_id,
            "statut": corps.statut,
            "correction": corps.correction.strip(),
            "par": admin_courant.id,
        },
    )
    db.commit()
    journal.info(
        "Signalement %s clos en « %s » par le compte %s.",
        signalement_id,
        corps.statut,
        admin_courant.id,
    )
    return next(
        s for s in lister_signalements(admin_courant, db) if s.id == signalement_id
    )


# ---------------------------------------------------------------------
# Suspendre, reactiver, supprimer un compte
#
# DEUX GESTES QUI NE SE VALENT PAS. Suspendre est reversible et ne perd
# rien : le compte existe, il ne peut plus entrer. Supprimer est
# definitif. C'est pourquoi la suspension exige un motif et la
# suppression une confirmation explicite du code du compte.
# ---------------------------------------------------------------------


def _proteger_le_dernier_administrateur(
    db: Session, cible: Utilisateur, geste: str
) -> None:
    """Refuse de retirer le dernier administrateur.

    FERMER LA PORTE A CLEF DE L'INTERIEUR. Sans ce controle, suspendre
    ou supprimer l'unique compte d'administration rendrait la console
    definitivement inaccessible : il n'existe aucune route pour en
    fabriquer un autre — le premier administrateur nait d'un script
    lance sur le serveur, et ce script suppose qu'on y ait acces.

    La regle porte sur le DERNIER administrateur, pas sur « le compte
    admin ». Elle continue donc de tenir le jour ou il y en aura
    plusieurs, sans qu'on ait a la reecrire.
    """
    if cible.role != "admin":
        return

    restants = db.execute(
        text(
            "SELECT count(*) FROM utilisateur "
            "WHERE role = 'admin' AND id <> :id AND suspendu_le IS NULL"
        ),
        {"id": cible.id},
    ).scalar()

    if not restants:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Impossible de {geste} le dernier administrateur : plus "
            "personne ne pourrait administrer l'application. Nommez un "
            "autre administrateur d'abord.",
        )


@routeur.post("/utilisateurs/{utilisateur_id}/suspendre")
def suspendre_compte(
    utilisateur_id: int,
    corps: SuspensionEntree,
    admin: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> UtilisateurSortie:
    """Ferme l'acces sans rien effacer.

    LE MOTIF EST OBLIGATOIRE. Une suspension sans raison rend toute
    reactivation arbitraire : celui qui la leve ne sait pas ce qu'il
    leve, et celui qui la subit ne peut pas la contester.
    """
    cible = db.get(Utilisateur, utilisateur_id)
    if cible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")

    if cible.id == admin.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Vous ne pouvez pas suspendre votre propre compte.",
        )
    _proteger_le_dernier_administrateur(db, cible, "suspendre")

    cible.suspendu_le = datetime.datetime.now(datetime.timezone.utc)
    cible.suspendu_motif = corps.motif.strip()
    db.commit()
    journal.info(
        "Compte %s suspendu par %s : %s", cible.id, admin.id, corps.motif.strip()
    )
    return UtilisateurSortie.model_validate(cible)


@routeur.post("/utilisateurs/{utilisateur_id}/reactiver")
def reactiver_compte(
    utilisateur_id: int,
    admin: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> UtilisateurSortie:
    """Rouvre l'acces. Le motif de suspension est efface avec elle."""
    cible = db.get(Utilisateur, utilisateur_id)
    if cible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")

    cible.suspendu_le = None
    cible.suspendu_motif = None
    db.commit()
    journal.info("Compte %s reactive par %s.", cible.id, admin.id)
    return UtilisateurSortie.model_validate(cible)


@routeur.delete("/utilisateurs/{utilisateur_id}", status_code=status.HTTP_204_NO_CONTENT)
def supprimer_compte(
    utilisateur_id: int,
    admin: Utilisateur = Depends(administrateur),
    db: Session = Depends(get_db),
) -> None:
    """Supprime definitivement un compte.

    CE QUI PART AVEC LUI : ses conversations, ses messages, ses favoris,
    ses annotations, son avis et ses demandes d'abonnement. Ce sont ses
    donnees personnelles, et les conserver apres suppression irait
    contre l'engagement de confidentialite du produit.

    CE QUI SURVIT : ses signalements, dont l'auteur est simplement
    anonymise. Le registre des incidents est un dispositif de
    protection ; un registre qu'un compte supprime peut vider ne prouve
    rien le jour ou il faudrait s'en servir.

    CE QUI L'EMPECHE : avoir depose ou valide un texte du corpus. Le nom
    du juriste figure dans la table de provenance publiee — c'est la
    chaine de responsabilite qui permet de repondre d'une citation
    contestee. Un tel compte se SUSPEND, il ne se supprime pas. La
    contrainte est posee en base (ON DELETE RESTRICT) autant qu'ici :
    le controle applicatif donne un message clair, la contrainte
    garantit qu'aucune autre voie ne contourne la regle.
    """
    cible = db.get(Utilisateur, utilisateur_id)
    if cible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")

    if cible.id == admin.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Vous ne pouvez pas supprimer votre propre compte.",
        )
    _proteger_le_dernier_administrateur(db, cible, "supprimer")

    depots = db.execute(
        text(
            "SELECT count(*) FROM depot "
            "WHERE depose_par = :id OR decide_par = :id"
        ),
        {"id": cible.id},
    ).scalar()
    if depots:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ce compte a déposé ou validé {depots} texte(s) du corpus : son "
            "nom figure dans la table de provenance publiée, et l'effacer "
            "romprait la chaîne de responsabilité. Suspendez-le plutôt.",
        )

    courriel = cible.email
    db.delete(cible)
    db.commit()
    journal.info("Compte %s (%s) supprime par %s.", utilisateur_id, courriel, admin.id)
