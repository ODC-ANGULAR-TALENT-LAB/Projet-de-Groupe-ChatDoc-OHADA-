"""Interface unique vers le fournisseur d'embeddings.

Un seul endroit du code appelle ce fournisseur : l'ingestion pour
vectoriser les articles, la recherche pour vectoriser la question. Si le
fournisseur change ses prix ou ses conditions, ce fichier est le seul a
modifier - et les vecteurs deja calcules restent la propriete du projet.

Aucun fournisseur n'est designe par les documents du projet : il se
configure par EMBEDDING_URL, EMBEDDING_MODELE et EMBEDDING_DIMENSIONS.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time

import httpx

from app.config import parametres

journal = logging.getLogger(__name__)

DELAI_APPEL = 60

# Reprise sur depassement de cadence.
#
# HUIT ESSAIS, PAS SIX. Le plafond de l'offre gratuite se compte PAR
# MINUTE : six essais couvraient 124 secondes, ce qui retombait parfois
# dans la meme fenetre et faisait echouer la vectorisation pour de bon.
# Huit essais portent l'attente cumulee a plus de huit minutes, soit
# plusieurs fenetres — le plafond a le temps de se vider.
#
# Ces attentes ne penalisent que la vectorisation en masse. Une question
# d'utilisateur ne vectorise qu'une phrase et ne rencontre ce plafond
# que si le service est deja sature.
TENTATIVES_DEBIT = 8
ATTENTE_DEBIT = 4.0


def extraire_vecteurs(reponse: dict, attendus: int) -> list[list[float]]:
    """Lit les vecteurs quelle que soit la forme rendue par le fournisseur.

    On accepte les deux formes les plus repandues plutot que d'en
    imposer une. Le controle du nombre n'est pas cosmetique : un vecteur
    manquant decalerait l'appariement et attribuerait silencieusement le
    mauvais embedding a chaque article suivant.
    """
    if isinstance(reponse, dict) and isinstance(reponse.get("data"), list):
        vecteurs = [element["embedding"] for element in reponse["data"]]
    elif isinstance(reponse, dict) and isinstance(reponse.get("embeddings"), list):
        vecteurs = reponse["embeddings"]
    else:
        raise RuntimeError(
            "Reponse du fournisseur d'embeddings non reconnue. "
            "Adapte extraire_vecteurs() a son format."
        )

    if len(vecteurs) != attendus:
        raise RuntimeError(
            f"Le fournisseur a renvoye {len(vecteurs)} vecteurs pour "
            f"{attendus} textes envoyes."
        )
    return vecteurs


def vecteur_simule(contenu: str, dimensions: int | None = None) -> list[float]:
    """Vecteur pseudo-aleatoire deterministe, derive du texte.

    Sert UNIQUEMENT a verifier la tuyauterie : insertion, index,
    requetes. Ces vecteurs ne portent aucun sens, donc la recherche
    qu'ils alimentent ne vaut rien. Le determinisme importe malgre tout :
    la meme question doit produire le meme vecteur d'un appel a l'autre.
    """
    dimensions = dimensions or parametres.embedding_dimensions
    graine = hashlib.sha256(contenu.encode("utf-8")).digest()
    valeurs: list[float] = []
    while len(valeurs) < dimensions:
        graine = hashlib.sha256(graine).digest()
        for position in range(0, len(graine), 4):
            if len(valeurs) >= dimensions:
                break
            (entier,) = struct.unpack("<I", graine[position : position + 4])
            valeurs.append(entier / 2**32 - 0.5)
    norme = sum(valeur * valeur for valeur in valeurs) ** 0.5
    return [valeur / norme for valeur in valeurs]


def calculer_embeddings(
    textes: list[str],
    simuler: bool = False,
    tentatives: int = 1,
) -> list[list[float]]:
    """Vectorise une liste de textes.

    `tentatives` VAUT UN PAR DEFAUT, ET CE DEFAUT EST LE POINT.

    Cette fonction sert deux appelants aux exigences opposees. La
    vectorisation en masse peut patienter des minutes : elle a tout le
    temps, et abandonner lui coute des appels deja payes. La recherche,
    elle, traite la question d'un utilisateur qui attend devant son
    ecran ; mieux vaut basculer aussitot en recherche lexicale que le
    faire patienter.

    Avoir mis la reprise ici sans la rendre optionnelle a fait attendre
    jusqu'a seize minutes une simple question — le serveur ne repondait
    tout simplement jamais. Le defaut prudent est donc de ne PAS
    reessayer ; c'est a l'appelant qui peut se le permettre de le
    demander.
    """
    if simuler:
        return [vecteur_simule(texte) for texte in textes]

    if not parametres.embeddings_configures:
        raise RuntimeError(
            "Fournisseur d'embeddings non configure : renseigne "
            "EMBEDDING_URL, EMBEDDING_MODELE et EMBEDDING_API_KEY dans "
            ".env. Les valeurs d'exemple ne comptent pas."
        )

    charge = {
            "model": parametres.embedding_modele,
            "input": textes,
            # LA DIMENSION EST DEMANDEE EXPLICITEMENT, jamais laissee au
            # defaut du fournisseur. `gemini-embedding-001` rend 3072
            # dimensions quand on ne dit rien, et la colonne est declaree
            # `vector(1536)` : l'insertion echouerait article par
            # article, apres avoir paye tous les appels.
            #
            # Le champ est compris aussi bien par la couche compatible de
            # Gemini que par OpenAI, dont les modeles v3 acceptent la
            # meme troncature. Il n'y a donc pas de fournisseur pour
            # lequel l'envoyer soit une erreur.
        "dimensions": parametres.embedding_dimensions,
    }

    # LA CADENCE EST LA CONTRAINTE, PAS LE VOLUME. Vectoriser 5 563
    # articles ne coute que quelques centimes, mais les offres gratuites
    # plafonnent le nombre d'appels par minute. Sans cette reprise, la
    # vectorisation s'arretait au DEUXIEME lot : le script est certes
    # reprenable, mais il fallait le relancer a la main indefiniment.
    #
    # L'attente double a chaque essai. Un plafond par minute se vide de
    # lui-meme ; il suffit de lui en laisser le temps.
    reponse = None
    for tentative in range(max(1, tentatives)):
        reponse = httpx.post(
            parametres.embedding_url,
            headers={
                "authorization": f"Bearer {parametres.cle_embeddings}",
                "content-type": "application/json",
            },
            json=charge,
            timeout=DELAI_APPEL,
        )

        if reponse.status_code != 429:
            break

        # `tentatives`, PAS la constante : avec un seul essai demande,
        # comparer au maximum global ferait patienter quatre secondes
        # avant un abandon deja decide.
        if tentative < tentatives - 1:
            attente = ATTENTE_DEBIT * (2**tentative)
            journal.warning(
                "Débit trop rapide (HTTP 429), pause de %.0f s avant reprise.",
                attente,
            )
            time.sleep(attente)

    if reponse.status_code >= 400:
        raise RuntimeError(_diagnostic(reponse))

    return extraire_vecteurs(reponse.json(), len(textes))


def _diagnostic(reponse: httpx.Response) -> str:
    """Traduit un refus du fournisseur en message actionnable.

    Un HTTPStatusError brut n'apprend rien : "429 Too Many Requests"
    peut aussi bien signifier un debit trop rapide qu'un compte sans
    credit. La difference change entierement ce qu'il faut faire.
    """
    try:
        erreur = reponse.json().get("error", {})
        message = str(erreur.get("message", ""))
        # LE CODE N'EST PAS TOUJOURS UNE CHAINE. Certains fournisseurs y
        # mettent le statut HTTP sous forme d'ENTIER — « "code": 429 » —
        # la ou d'autres ecrivent « "code": "insufficient_quota" ». Sans
        # cette conversion, le test d'appartenance ci-dessous levait un
        # TypeError : la fonction chargee d'EXPLIQUER la panne plantait
        # a son tour, et le message du fournisseur — le seul
        # renseignement utile — etait perdu.
        code = str(erreur.get("code") or erreur.get("type") or "")
    except Exception:  # noqa: BLE001 - reponse non JSON
        message, code = reponse.text[:200], ""

    if reponse.status_code == 401:
        return (
            "Cle d'API refusee par le fournisseur d'embeddings. Verifie "
            "EMBEDDING_API_KEY dans .env."
        )
    if "quota" in code or "credit" in code or "billing" in message.lower():
        return (
            "Le compte du fournisseur d'embeddings n'a plus de credit. "
            "Approvisionne-le, puis relance la vectorisation. "
            f"(message du fournisseur : {message[:120]})"
        )
    if reponse.status_code == 429:
        return (
            "Debit trop rapide vers le fournisseur d'embeddings. Relance "
            "la vectorisation : elle reprend ou elle s'est arretee."
        )
    return (
        f"Le fournisseur d'embeddings a refuse l'appel "
        f"(HTTP {reponse.status_code}) : {message[:150]}"
    )


def formater_vecteur(vecteur: list[float]) -> str:
    """Litteral accepte par pgvector : [0.1,0.2,...]"""
    return "[" + ",".join(repr(float(valeur)) for valeur in vecteur) + "]"
