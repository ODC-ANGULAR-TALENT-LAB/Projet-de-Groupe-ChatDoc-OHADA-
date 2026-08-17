"""Lire la reponse au fil de l'eau, dans un JSON encore incomplet.

LE PROBLEME. Le modele rend un objet JSON contraint par un schema :
{"reponse": "...", "citations": [...], "confiance": "...", ...}. C'est
la garantie centrale du produit et on n'y touche pas (voir llm.py). Mais
pour afficher la reponse au fil de l'eau, il faut extraire le champ
"reponse" d'un document qui n'est pas encore valide — json.loads() ne
peut rien en faire tant qu'il manque une accolade.

CE MODULE EST DELIBEREMENT FAILLIBLE, ET C'EST SANS CONSEQUENCE. Il fait
de son mieux pour lire le champ "reponse" en cours d'ecriture ; s'il n'y
arrive pas, il rend une chaine vide et l'interface se contente de son
indicateur d'attente. LE JSON COMPLET, lui, est parse normalement a la
fin, et c'est LUI qui fait foi : citations validees, confiance, refus.

Autrement dit : le streaming est un confort de presentation, jamais une
source de verite. Aucune citation n'est diffusee ici — elles n'existent
qu'apres validation serveur, et montrer une preuve qu'on pourrait
ensuite retirer serait pire que de faire patienter.
"""

from __future__ import annotations

# Sequences d'echappement JSON, hors \uXXXX traite a part.
ECHAPPEMENTS = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

CLE = '"reponse"'


def extraire_reponse_partielle(brut: str) -> str:
    """Valeur du champ "reponse" dans un JSON possiblement tronque.

    Rend la chaine vide tant que le champ n'a pas commence, ou si quoi
    que ce soit d'inattendu se presente. Ne leve jamais.
    """
    debut = brut.find(CLE)
    if debut == -1:
        return ""

    # Aller jusqu'au guillemet ouvrant de la valeur, en sautant les
    # espaces et le deux-points.
    indice = debut + len(CLE)
    while indice < len(brut) and brut[indice] in " \t\r\n:":
        indice += 1
    if indice >= len(brut) or brut[indice] != '"':
        return ""
    indice += 1

    morceaux: list[str] = []
    while indice < len(brut):
        caractere = brut[indice]

        if caractere == '"':
            # Fin de la valeur : la chaine est complete.
            break

        if caractere != "\\":
            morceaux.append(caractere)
            indice += 1
            continue

        # Echappement. S'il est coupe en deux par la frontiere d'un
        # fragment, on s'arrete la : le prochain appel le verra entier.
        if indice + 1 >= len(brut):
            break
        suivant = brut[indice + 1]

        if suivant == "u":
            if indice + 6 > len(brut):
                break
            try:
                morceaux.append(chr(int(brut[indice + 2 : indice + 6], 16)))
            except ValueError:
                break
            indice += 6
            continue

        if suivant not in ECHAPPEMENTS:
            break
        morceaux.append(ECHAPPEMENTS[suivant])
        indice += 2

    return "".join(morceaux)
