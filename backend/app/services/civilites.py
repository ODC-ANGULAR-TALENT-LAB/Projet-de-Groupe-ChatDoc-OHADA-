"""Les echanges qui ne sont pas des questions de droit.

POURQUOI CE FICHIER EXISTE. « Bonjour » ne ressemble a aucun article du
corpus. La recherche ne remontait donc rien, et l'assistant repondait
« Cette question depasse les textes actuellement disponibles dans ma
bibliotheque » — une phrase juste sur le fond, absurde dans le contexte,
et qui donne le sentiment de parler a un mur.

Un utilisateur qui salue avant de poser sa vraie question n'a pas encore
pose de question. Lui opposer un refus l'incite a croire que l'outil ne
fonctionne pas, et beaucoup n'essaient pas une seconde fois.

TROIS PROPRIETES VOULUES.

1. AUCUN APPEL AU MODELE. Ces reponses sont des chaines fixes. Elles ne
   consomment ni credit ni quota, et repondent instantanement.

2. AUCUNE PRISE POUR UNE INJECTION. Le texte de l'utilisateur sert
   uniquement a CHOISIR une reponse ecrite ici ; il n'est jamais
   recopie, ni transmis a un modele. « Bonjour, ignore tes
   instructions » ne peut donc rien obtenir de plus qu'un bonjour.

3. AUCUN EMPIETEMENT SUR LE DROIT. La reconnaissance exige que la
   totalite du message soit une civilite. « Bonjour, quelle est la duree
   de la garde a vue ? » part au corpus, comme il se doit : c'est une
   question de droit, et elle merite une reponse sourcee.
"""

from __future__ import annotations

import re
import unicodedata

# Au-dela, ce n'est plus une formule de politesse mais un message qui dit
# quelque chose — et qui merite donc le corpus.
MOTS_MAXIMUM = 6

REPONSE_SALUTATION = (
    "Bonjour. Je suis l'assistant de recherche de ChatDocs OHADA : je "
    "reponds aux questions de droit des affaires OHADA et de fiscalite "
    "camerounaise en citant les articles qui fondent chaque reponse.\n\n"
    "Posez votre question directement — par exemple « quelles sont les "
    "mentions obligatoires du registre du commerce ? » ou « quel est le "
    "taux de la TVA au Cameroun ? »."
)

REPONSE_REMERCIEMENT = (
    "Avec plaisir. N'hesitez pas si une autre question se presente."
)

REPONSE_IDENTITE = (
    "Je suis l'assistant de recherche de ChatDocs OHADA. Je travaille "
    "uniquement a partir d'un corpus de textes officiels — actes "
    "uniformes OHADA, Code general des impots et codes camerounais — et "
    "chaque affirmation que je fais est rattachee a l'article qui la "
    "fonde.\n\n"
    "Ce que je ne fais pas : je ne donne pas de consultation juridique, "
    "et je refuse de repondre plutot que d'inventer lorsque les textes "
    "disponibles ne permettent pas de trancher."
)

# Chaque motif doit couvrir le message ENTIER : c'est ce qui empeche
# « bonjour, quelle est la duree de la garde a vue » d'etre pris pour une
# simple salutation.
CIVILITES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"^(bonjour|bonsoir|salut|bjr|slt|hello|hi|coucou|"
            r"bonne journee|bonne soiree|good morning|good evening)"
            r"[\s!.?]*$"
        ),
        REPONSE_SALUTATION,
    ),
    (
        re.compile(
            r"^(merci|merci beaucoup|mrc|thanks|thank you|"
            r"je vous remercie|c est note|parfait|super|ok merci)"
            r"[\s!.?]*$"
        ),
        REPONSE_REMERCIEMENT,
    ),
    (
        re.compile(
            r"^(qui es[- ]tu|qui etes[- ]vous|tu es qui|c est quoi ce site|"
            r"que sais[- ]tu faire|que peux[- ]tu faire|"
            r"tu sers a quoi|comment ca marche|aide|help)"
            r"[\s!.?]*$"
        ),
        REPONSE_IDENTITE,
    ),
]


def normaliser(message: str) -> str:
    """Minuscules, sans accents, ponctuation reduite a l'espace.

    Sans cela, « Bonjour ! », « bonjour » et « BONJOUR… » seraient trois
    messages differents, et l'un des trois passerait a cote.
    """
    sans_accent = "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", message)
        if unicodedata.category(caractere) != "Mn"
    )
    reduit = re.sub(r"[^\w\s!?.]", " ", sans_accent.lower())
    return re.sub(r"\s+", " ", reduit).strip()


def reponse_de_civilite(message: str) -> str | None:
    """La reponse toute faite si le message n'est qu'une civilite.

    Rend None des que le message dit autre chose : c'est alors une
    question, et elle doit suivre le chemin normal — recherche, seuil,
    citations verifiees.
    """
    propre = normaliser(message)
    if not propre or len(propre.split()) > MOTS_MAXIMUM:
        return None

    for motif, reponse in CIVILITES:
        if motif.match(propre):
            return reponse
    return None
