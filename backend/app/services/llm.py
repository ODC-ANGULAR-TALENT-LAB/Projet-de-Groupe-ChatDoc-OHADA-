"""E.3 - Interface unique vers le fournisseur LLM.

Tout appel au modele passe par ce fichier. Si le fournisseur change ses
prix ou ses conditions, c'est le seul fichier a modifier : le corpus et
les embeddings restent la propriete du projet.

LA CLE NE QUITTE JAMAIS LE SERVEUR. Le frontend n'appelle jamais le
fournisseur directement.

DEUX ECARTS PAR RAPPORT AU CODE DU GUIDE, tous deux imposes par l'API
actuelle ou par la fiabilite du produit :

1. Pas de `temperature`. Le parametre a ete retire des modeles Claude
   actuels et une requete qui le porte est rejetee (400). La sobriete
   des reponses se pilote par le prompt et par le niveau d'effort.

2. Sortie JSON contrainte cote serveur (`output_config.format`) plutot
   qu'un JSON demande en prose puis recupere par json.loads() sur du
   texte libre. Pour un produit dont la garantie centrale est la
   validation des citations, laisser le format dependre de la bonne
   volonte du modele est le maillon faible : ici le schema est impose.
"""

from __future__ import annotations

import json
import logging

import anthropic

from app.config import parametres

journal = logging.getLogger(__name__)

# Schema impose au modele. Tous les champs sont requis : "mise_en_garde"
# vaut la chaine vide quand il n'y a rien a signaler, ce qui evite au
# frontend d'avoir a distinguer absent et vide.
SCHEMA_REPONSE = {
    "type": "object",
    "properties": {
        "reponse": {
            "type": "string",
            "description": "Reponse en francais, fondee uniquement sur les articles fournis.",
        },
        "citations": {
            "type": "array",
            "description": "Articles qui fondent la reponse. Vide si aucun ne la fonde.",
            "items": {
                "type": "object",
                "properties": {
                    "article_id": {
                        "type": "integer",
                        "description": "id EXACT d'un article present dans le contexte fourni.",
                    },
                    "extrait": {
                        "type": "string",
                        "description": "Passage exact de l'article, recopie sans reformulation.",
                    },
                    "pourquoi": {
                        "type": "string",
                        "description": "En une phrase, ce que cet article etablit.",
                    },
                },
                "required": ["article_id", "extrait", "pourquoi"],
                "additionalProperties": False,
            },
        },
        "confiance": {
            "type": "string",
            "enum": ["elevee", "moyenne", "insuffisante"],
        },
        "mise_en_garde": {
            "type": "string",
            "description": "Reserve ou nuance a signaler ; chaine vide si aucune.",
        },
    },
    "required": ["reponse", "citations", "confiance", "mise_en_garde"],
    "additionalProperties": False,
}

# Reponse rendue quand le fournisseur echoue. Le produit refuse plutot
# que d'inventer : une panne ne doit jamais produire une reponse fausse.
REFUS_TECHNIQUE = {
    "reponse": "Je ne parviens pas a produire une reponse fiable pour le moment.",
    "citations": [],
    "confiance": "insuffisante",
    "mise_en_garde": "",
    "refus": True,
}


def appeler_llm_flux(
    systeme: str,
    utilisateur: str,
    schema: dict | None = None,
    defaut: dict | None = None,
):
    """Comme appeler_llm, mais en rendant la reponse au fil de l'eau.

    Generateur : produit des couples ("texte", partiel) au fur et a
    mesure, puis un dernier couple ("fin", dictionnaire complet).

    LE DERNIER COUPLE SEUL FAIT FOI. Les fragments intermediaires sont
    lus dans un JSON encore incomplet (voir flux_json.py) : c'est une
    commodite d'affichage, faillible et sans consequence. Les citations
    n'y figurent JAMAIS — elles n'existent qu'apres validation serveur,
    et diffuser une preuve qu'on pourrait ensuite retirer serait pire
    que de faire patienter.
    """
    from app.services.flux_json import extraire_reponse_partielle

    schema = schema or SCHEMA_REPONSE
    repli = dict(defaut if defaut is not None else REFUS_TECHNIQUE)

    brut = ""
    dernier = ""
    try:
        with _client().messages.stream(
            model=parametres.llm_modele,
            max_tokens=parametres.llm_max_tokens,
            system=systeme,
            messages=[{"role": "user", "content": utilisateur}],
            output_config={
                "effort": parametres.llm_effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        ) as flux:
            for fragment in flux.text_stream:
                brut += fragment
                partiel = extraire_reponse_partielle(brut)
                # On n'emet que si le texte a AVANCE : un affichage qui
                # reculerait donnerait une impression de bafouillage.
                if len(partiel) > len(dernier):
                    dernier = partiel
                    yield ("texte", partiel)

            message = flux.get_final_message()
    except anthropic.APIError as erreur:
        journal.error("Appel LLM en flux en echec : %s", erreur)
        yield ("fin", repli)
        return

    if message.stop_reason in ("refusal", "max_tokens"):
        journal.warning("Flux interrompu (%s).", message.stop_reason)
        yield ("fin", repli)
        return

    try:
        yield ("fin", json.loads(brut))
    except json.JSONDecodeError:
        journal.error("Reponse en flux non conforme au schema impose.")
        yield ("fin", repli)


def _client() -> anthropic.Anthropic:
    if not parametres.llm_api_key:
        raise RuntimeError("LLM_API_KEY absent du .env.")
    return anthropic.Anthropic(api_key=parametres.llm_api_key)


def appeler_llm(
    systeme: str,
    utilisateur: str,
    schema: dict | None = None,
    defaut: dict | None = None,
) -> dict:
    """Appelle le modele et rend un dictionnaire conforme au schema.

    `systeme` porte les regles ; `utilisateur` porte les articles et la
    question. Les deux restent SEPARES : la question de l'utilisateur
    n'est jamais concatenee au prompt systeme.

    `schema` et `defaut` permettent a un autre usage du modele — le
    resume d'une modification pour le juriste, par exemple — de passer
    par ce meme fichier plutot que d'ouvrir une seconde porte vers le
    fournisseur. La regle du projet est qu'il n'existe qu'un point de
    sortie : changer de fournisseur ne doit toucher qu'ici.
    """
    schema = schema or SCHEMA_REPONSE
    repli = dict(defaut if defaut is not None else REFUS_TECHNIQUE)

    try:
        reponse = _client().messages.create(
            model=parametres.llm_modele,
            max_tokens=parametres.llm_max_tokens,
            system=systeme,
            messages=[{"role": "user", "content": utilisateur}],
            output_config={
                "effort": parametres.llm_effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        )
    except anthropic.APIError as erreur:
        journal.error("Appel LLM en echec : %s", erreur)
        return repli

    if reponse.stop_reason == "refusal":
        # Les classificateurs du fournisseur ont decline la requete.
        journal.warning("Requete declinee par le fournisseur.")
        return repli

    if reponse.stop_reason == "max_tokens":
        # Reponse tronquee : le JSON est incomplet, donc inexploitable.
        journal.warning("Reponse tronquee (max_tokens=%s).", parametres.llm_max_tokens)
        return repli

    texte = next((bloc.text for bloc in reponse.content if bloc.type == "text"), "")
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        # Ne devrait pas arriver avec un schema impose ; on refuse plutot
        # que de rendre au frontend quelque chose d'inexploitable.
        journal.error("Reponse non conforme au schema impose.")
        return repli
