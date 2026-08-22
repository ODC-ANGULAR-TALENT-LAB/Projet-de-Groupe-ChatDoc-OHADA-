"""E.3 - Interface unique vers le fournisseur LLM.

Tout appel au modele passe par ce fichier. Si le fournisseur change ses
prix ou ses conditions, c'est le seul fichier a modifier : le corpus et
les embeddings restent la propriete du projet. C'est precisement ce qui
s'est verifie ici — le passage d'un fournisseur a l'autre n'a touche
que ce fichier, sans que rag.py, conformite.py, reformulation.py ni
analyse_depot.py aient une ligne a changer.

LA CLE NE QUITTE JAMAIS LE SERVEUR. Le frontend n'appelle jamais le
fournisseur directement.

TROIS PARTIS PRIS, imposes par l'API ou par la fiabilite du produit :

1. Pas de `temperature`. La sobriete des reponses se pilote par le
   prompt, pas par un reglage d'echantillonnage.

2. Sortie JSON contrainte COTE SERVEUR (`responseSchema`) plutot qu'un
   JSON demande en prose puis recupere par json.loads() sur du texte
   libre. Pour un produit dont la garantie centrale est la validation
   des citations, laisser le format dependre de la bonne volonte du
   modele serait le maillon faible.

3. Appels HTTP directs plutot qu'un SDK. httpx est deja une dependance
   du projet (embeddings.py), la surface utilisee ici tient en deux
   requetes, et un SDK de fournisseur ajoute une dependance qui evolue
   a son rythme pour un benefice nul a cette echelle.
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from app.config import parametres

journal = logging.getLogger(__name__)

# Codes qui meritent une seconde chance : saturation passagere du
# fournisseur (503) et depassement de cadence (429). Tous les autres
# echecs sont definitifs — une cle invalide ne deviendra pas valide en
# reessayant, et insister ne ferait qu'allonger l'attente.
CODES_REESSAYABLES = {429, 503}

# Niveaux de reflexion que l'API reconnait. LLM_EFFORT peut porter des
# valeurs heritees d'un autre fournisseur ("xhigh", "max") : les
# transmettre ferait echouer la requete en 400. On n'envoie donc le
# reglage que s'il est compris, et on laisse le defaut sinon.
NIVEAUX_REFLEXION = {"low", "medium", "high"}

# Trois tentatives au plus, espacees d'une attente croissante. Au-dela,
# on rend la main : l'utilisateur attend devant sa question, et le
# produit sait refuser proprement.
TENTATIVES = 3
ATTENTE_INITIALE = 1.5

# Racine de l'API. Configurable par URL_FOURNISSEUR : c'est ce qui
# permet de basculer vers un mandataire ou une autre region sans
# retoucher le code.
URL_ANTHROPIC = "https://api.anthropic.com/v1"
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta"

# Version d'API demandee. Figee volontairement : une API qui evolue ne
# doit pas changer le comportement du produit sans qu'on l'ait decide.
VERSION_ANTHROPIC = "2023-06-01"

# Un appel de redaction depasse couramment dix secondes ; le delai doit
# laisser la place au raisonnement du modele sans pour autant retenir un
# ouvrier indefiniment si le fournisseur ne repond plus.
DELAI_APPEL = 120.0

# Schema impose au modele. Tous les champs sont requis : "mise_en_garde"
# vaut la chaine vide quand il n'y a rien a signaler, ce qui evite au
# frontend d'avoir a distinguer absent et vide.
SCHEMA_REPONSE = {
    "type": "object",
    "properties": {
        "reponse": {
            "type": "string",
            # LA DESCRIPTION DU SCHEMA EST LUE PAR LE MODELE au meme titre
            # que le prompt systeme. La laisser muette sur la forme
            # revenait a demander une note structuree d'un cote et une
            # simple chaine de l'autre : le modele suivait la consigne la
            # plus proche du champ, donc celle-ci.
            "description": (
                "Reponse en francais, fondee uniquement sur les articles "
                "fournis. Structuree comme une note juridique : reponse "
                "directe en tete, puis sections introduites par '## ', "
                "listes numerotees pour les etapes ou conditions "
                "cumulatives, **gras** sur le terme ou le chiffre qui "
                "porte la reponse, et reference entre parentheses apres "
                "chaque affirmation, par exemple (art. 12 AUSCGIE)."
            ),
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

# Motifs d'arret qui rendent la reponse inexploitable. "STOP" est le
# seul cas nominal ; tout le reste laisse un JSON tronque ou vide.
ARRETS_FAUTIFS = {"MAX_TOKENS", "SAFETY", "RECITATION", "BLOCKLIST", "OTHER"}

# Les equivalents chez l'autre fournisseur. « end_turn » est le seul cas
# nominal ; « max_tokens » laisse un JSON tronque et « refusal » ne rend
# rien d'exploitable.
ARRETS_FAUTIFS_ANTHROPIC = {"max_tokens", "refusal"}

# Correspondance des types entre le JSON Schema du projet et le dialecte
# du fournisseur, qui les veut en capitales.
TYPES = {
    "object": "OBJECT",
    "array": "ARRAY",
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
}

# Mots-cles que le fournisseur REFUSE, et qui font echouer la requete en
# 400 s'ils sont transmis. `additionalProperties` en fait partie : il est
# porte par SCHEMA_REPONSE, ou il exprime une intention legitime — aucun
# champ en trop — que ce dialecte ne sait simplement pas dire.
CLES_IGNOREES = {"additionalProperties", "$schema", "definitions", "$defs"}


def convertir_schema(schema: dict) -> dict:
    """Traduit un JSON Schema vers le dialecte attendu par l'API.

    POURQUOI UNE TRADUCTION PLUTOT QUE D'ECRIRE LE SCHEMA AU FORMAT DU
    FOURNISSEUR. SCHEMA_REPONSE est lu par des humains, repris par les
    tests, et documente le contrat de sortie du produit. L'ecrire dans
    le dialecte d'un fournisseur particulier ferait payer un changement
    de fournisseur a tout le monde ; la traduction, elle, tient dans
    cette fonction.

    Elle est RECURSIVE parce que le schema l'est : les citations sont un
    tableau d'objets, et leurs proprietes doivent etre converties comme
    celles du premier niveau.
    """
    converti: dict = {}
    for cle, valeur in schema.items():
        if cle in CLES_IGNOREES:
            continue
        if cle == "type":
            converti["type"] = TYPES.get(valeur, str(valeur).upper())
        elif cle == "properties":
            converti["properties"] = {
                nom: convertir_schema(sous) for nom, sous in valeur.items()
            }
        elif cle == "items":
            converti["items"] = convertir_schema(valeur)
        else:
            converti[cle] = valeur
    return converti


def _corps(systeme: str, utilisateur: str, schema: dict, flux: bool = False) -> dict:
    """Le corps de la requete, dans le dialecte du fournisseur en service.

    LES REGLES ET LA DONNEE RESTENT SEPAREES, quel que soit le
    protocole : `systeme` va dans le champ des instructions,
    `utilisateur` dans celui du message. C'est cette frontiere qui
    garantit qu'une question contenant « ignore les instructions
    precedentes » n'atteint jamais les regles.
    """
    if _anthropic():
        return _corps_anthropic(systeme, utilisateur, schema, flux)
    return _corps_gemini(systeme, utilisateur, schema)


def _anthropic() -> bool:
    return parametres.llm_protocole.strip().lower() == "anthropic"


def _corps_anthropic(
    systeme: str, utilisateur: str, schema: dict, flux: bool
) -> dict:
    """Le schema part TEL QUEL : ce dialecte lit le JSON Schema standard.

    Aucune traduction n'est donc necessaire ici — contrairement a
    l'autre protocole, qui veut ses types en capitales et refuse
    `additionalProperties`.
    """
    corps: dict = {
        "model": parametres.llm_modele,
        "max_tokens": parametres.llm_max_tokens,
        "system": systeme,
        "messages": [{"role": "user", "content": utilisateur}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    if flux:
        corps["stream"] = True
    return corps


def _corps_gemini(systeme: str, utilisateur: str, schema: dict) -> dict:
    reglages: dict = {
        "responseMimeType": "application/json",
        "responseSchema": convertir_schema(schema),
        "maxOutputTokens": parametres.llm_max_tokens,
    }

    # LE NIVEAU DE REFLEXION DECIDE DU TEMPS DE REPONSE, ET DE TRES LOIN.
    #
    # Laisse a son defaut, ce modele raisonne longuement : une question
    # accompagnee de huit articles depassait CENT VINGT SECONDES, donc le
    # delai d'attente, et l'utilisateur ne recevait jamais rien. En
    # « low », la meme requete revient en quelques secondes.
    #
    # Le champ se niche dans `thinkingConfig` ; place directement dans
    # `generationConfig`, il est rejete en 400 avec « Unknown name
    # thinkingLevel » — ce qui donne l'impression que le modele ne sait
    # pas le faire.
    if parametres.llm_effort in NIVEAUX_REFLEXION:
        reglages["thinkingConfig"] = {"thinkingLevel": parametres.llm_effort}

    return {
        "systemInstruction": {"parts": [{"text": systeme}]},
        "contents": [{"role": "user", "parts": [{"text": utilisateur}]}],
        "generationConfig": reglages,
    }


def _url(methode: str) -> str:
    """L'adresse a appeler, selon le protocole en service."""
    if not parametres.llm_api_key:
        raise RuntimeError("LLM_API_KEY absent du .env.")

    if _anthropic():
        racine = (parametres.url_fournisseur or URL_ANTHROPIC).rstrip("/")
        return f"{racine}/messages"

    # LA CLE VOYAGE EN PARAMETRE D'URL, parce que c'est ce que cette API
    # impose. Elle ne doit donc jamais etre journalisee : voir
    # _signaler(), qui ne consigne que le code et le message.
    racine = (parametres.url_fournisseur or URL_GEMINI).rstrip("/")
    return (
        f"{racine}/models/{parametres.llm_modele}:{methode}"
        f"?key={parametres.llm_api_key}"
    )


def _entetes() -> dict:
    """Les en-tetes, cle d'authentification comprise s'il y a lieu."""
    entetes = {"content-type": "application/json"}
    if _anthropic():
        entetes["x-api-key"] = parametres.llm_api_key
        entetes["anthropic-version"] = VERSION_ANTHROPIC
    return entetes


def _signaler(reponse: httpx.Response | None) -> None:
    """Journalise un echec sans jamais recopier l'URL, qui porte la cle."""
    if reponse is None:
        journal.error("Appel LLM : aucune reponse du fournisseur.")
        return
    try:
        message = reponse.json().get("error", {}).get("message", "")
    except ValueError:
        message = reponse.text[:200]
    journal.error("Appel LLM en echec (HTTP %s) : %s", reponse.status_code, message)


def _texte(charge: dict) -> str:
    """Recolle les fragments de texte d'une reponse.

    Le modele peut repartir sa sortie sur plusieurs blocs — et, sur les
    modeles a raisonnement, y glisser des blocs qui n'en sont pas
    (pensee, signatures). On ne garde que ce qui porte du texte.
    """
    if _anthropic():
        return "".join(
            bloc.get("text", "")
            for bloc in charge.get("content") or []
            if bloc.get("type") == "text"
        )

    candidats = charge.get("candidates") or []
    if not candidats:
        return ""
    parties = candidats[0].get("content", {}).get("parts") or []
    return "".join(partie.get("text", "") for partie in parties)


def _arret_fautif(charge: dict) -> str | None:
    """Le motif d'arret s'il rend la reponse inexploitable, sinon None.

    ON NE JUGE QUE SUR UN MOTIF EXPLICITE. Un fragment depourvu de
    `candidates` n'est pas une anomalie : le flux en emet pour porter la
    comptabilite des jetons. Traiter cette absence comme un echec
    faisait avorter des reponses parfaitement valides, au dernier
    fragment, apres les avoir affichees a l'utilisateur.
    """
    if _anthropic():
        motif = charge.get("stop_reason")
        return motif if motif in ARRETS_FAUTIFS_ANTHROPIC else None

    candidats = charge.get("candidates") or []
    if not candidats:
        return None
    motif = candidats[0].get("finishReason")
    return motif if motif in ARRETS_FAUTIFS else None


def _texte_du_fragment(charge: dict) -> str:
    """Le texte porte par UN fragment de flux.

    UN FLUX N'EST PAS UNE REPONSE DECOUPEE. Le premier protocole emet des
    evenements typés — ouverture de bloc, increment, fin — dont seuls les
    increments de texte portent de la prose. Lire ces fragments avec
    _texte(), qui attend la forme complete, ne rendrait jamais rien : le
    flux paraitrait muet, puis la reponse tomberait d'un bloc a la fin.
    """
    if not _anthropic():
        return _texte(charge)

    if charge.get("type") == "content_block_delta":
        delta = charge.get("delta") or {}
        if delta.get("type") == "text_delta":
            return delta.get("text", "")
    return ""


def _arret_du_fragment(charge: dict) -> str | None:
    """Le motif d'arret, lu la ou chaque protocole le place en flux."""
    if not _anthropic():
        return _arret_fautif(charge)

    if charge.get("type") == "message_delta":
        motif = (charge.get("delta") or {}).get("stop_reason")
        return motif if motif in ARRETS_FAUTIFS_ANTHROPIC else None
    return None


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

    corps = _corps(systeme, utilisateur, schema)
    reponse = None
    for tentative in range(TENTATIVES):
        try:
            reponse = httpx.post(
                _url("generateContent"),
                headers=_entetes(),
                json=corps,
                timeout=DELAI_APPEL,
            )
        except httpx.HTTPError as erreur:
            journal.error("Appel LLM injoignable : %s", erreur)
            return repli

        if reponse.status_code not in CODES_REESSAYABLES:
            break

        # L'offre gratuite sature regulierement. Sans cette reprise,
        # chaque pic de demande chez le fournisseur se traduisait par un
        # refus affiche a l'utilisateur, alors que la question etait
        # parfaitement traitable une seconde plus tard.
        if tentative < TENTATIVES - 1:
            attente = ATTENTE_INITIALE * (2**tentative)
            journal.warning(
                "Fournisseur saturé (HTTP %s), nouvelle tentative dans %.1f s.",
                reponse.status_code,
                attente,
            )
            time.sleep(attente)

    if reponse is None or reponse.status_code >= 400:
        _signaler(reponse)
        return repli

    charge = reponse.json()

    # Hors flux, une reponse vide est bien une anomalie : c'est l'unique
    # message, et il ne porte rien.
    #
    # ON JUGE SUR LE TEXTE EXTRAIT, PAS SUR UN CHAMP PARTICULIER. La
    # version precedente cherchait `candidates`, qui n'existe que chez un
    # des deux fournisseurs : apres bascule, toute reponse — pourtant
    # parfaitement valide — etait rejetee comme « aucun candidat ».
    texte = _texte(charge)
    motif = _arret_fautif(charge) or (None if texte else "reponse vide")
    if motif:
        # Tronquee ou refusee par les classificateurs : le JSON est
        # incomplet, donc inexploitable. On refuse plutot que de rendre
        # au frontend quelque chose qu'il ne saura pas lire.
        journal.warning("Reponse inexploitable (%s).", motif)
        return repli

    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        # Ne devrait pas arriver avec un schema impose.
        journal.error("Reponse non conforme au schema impose.")
        return repli


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
    motif = None

    try:
        # `alt=sse` demande un flux d'evenements ligne a ligne chez le
        # second fournisseur. Sans lui, son API rend un tableau JSON d'un
        # seul tenant : le streaming existerait sur le papier et
        # l'utilisateur attendrait quand meme la reponse entiere. Le
        # premier, lui, diffuse des qu'on pose `stream: true` dans le
        # corps.
        adresse = (
            _url("messages")
            if _anthropic()
            else _url("streamGenerateContent") + "&alt=sse"
        )
        with httpx.stream(
            "POST",
            adresse,
            headers=_entetes(),
            json=_corps(systeme, utilisateur, schema, flux=True),
            timeout=DELAI_APPEL,
        ) as flux:
            if flux.status_code >= 400:
                flux.read()
                _signaler(flux)
                yield ("fin", repli)
                return

            for ligne in flux.iter_lines():
                if not ligne.startswith("data:"):
                    continue
                fragment = ligne[5:].strip()
                if not fragment or fragment == "[DONE]":
                    continue
                try:
                    charge = json.loads(fragment)
                except json.JSONDecodeError:
                    continue

                brut += _texte_du_fragment(charge)
                motif = _arret_du_fragment(charge) or motif

                partiel = extraire_reponse_partielle(brut)
                # On n'emet que si le texte a AVANCE : un affichage qui
                # reculerait donnerait une impression de bafouillage.
                if len(partiel) > len(dernier):
                    dernier = partiel
                    yield ("texte", partiel)
    except httpx.HTTPError as erreur:
        journal.error("Appel LLM en flux en echec : %s", erreur)
        yield ("fin", repli)
        return

    if motif:
        journal.warning("Flux interrompu (%s).", motif)
        yield ("fin", repli)
        return

    try:
        yield ("fin", json.loads(brut))
    except json.JSONDecodeError:
        journal.error("Reponse en flux non conforme au schema impose.")
        yield ("fin", repli)
