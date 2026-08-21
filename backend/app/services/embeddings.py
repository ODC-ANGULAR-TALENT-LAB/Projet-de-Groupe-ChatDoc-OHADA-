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
import struct

import httpx

from app.config import parametres

DELAI_APPEL = 60


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


def calculer_embeddings(textes: list[str], simuler: bool = False) -> list[list[float]]:
    """Vectorise une liste de textes."""
    if simuler:
        return [vecteur_simule(texte) for texte in textes]

    if not parametres.embeddings_configures:
        raise RuntimeError(
            "Fournisseur d'embeddings non configure : renseigne "
            "EMBEDDING_URL, EMBEDDING_MODELE et EMBEDDING_API_KEY dans "
            ".env. Les valeurs d'exemple ne comptent pas."
        )

    reponse = httpx.post(
        parametres.embedding_url,
        headers={
            "authorization": f"Bearer {parametres.cle_embeddings}",
            "content-type": "application/json",
        },
        json={
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
        },
        timeout=DELAI_APPEL,
    )

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
        message = erreur.get("message", "")
        code = erreur.get("code") or erreur.get("type") or ""
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
