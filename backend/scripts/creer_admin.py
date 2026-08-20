"""Cree ou promeut un compte d'administration.

    python scripts/creer_admin.py

POURQUOI UN SCRIPT ET NON UNE ROUTE. Une route qui fabrique un
administrateur est une porte derobee : il suffit de l'atteindre pour
s'octroyer tous les droits. Le premier administrateur doit naitre d'un
geste posé sur le SERVEUR, par quelqu'un qui y a deja acces. Les
suivants se nomment depuis la console d'administration.

LE MOT DE PASSE N'EST NI GENERE NI AFFICHE. Il est demande a la saisie,
masque, confirme, puis immediatement hache en bcrypt. Il n'apparait
dans aucun journal, aucune sortie de terminal, aucun fichier, et aucun
historique de commandes — ce qui serait le cas s'il etait passe en
argument.

C'est la meme raison qui fait que `createsuperuser` de Django ou
`rails db:seed` demandent le mot de passe plutot que de l'inventer :
un secret qu'on transmet est un secret qu'on a compromis.

Le script est IDEMPOTENT. Relance sur une adresse existante, il propose
de promouvoir le compte sans toucher a son mot de passe. C'est le cas
courant : on veut donner les droits a quelqu'un qui a deja un compte.
"""

from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

# Le script vit dans backend/scripts/ ; l'application est un cran au-dessus.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import parametres  # noqa: E402
from app.db import FabriqueSession  # noqa: E402
from app.services.securite import hacher  # noqa: E402

# Meme plancher que l'inscription (schemas.py) : un administrateur ne
# doit pas etre protege moins bien qu'un utilisateur ordinaire.
LONGUEUR_MINIMALE = 8

RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def demander_email() -> str:
    while True:
        adresse = input("Adresse e-mail de l'administrateur : ").strip().lower()
        if RE_EMAIL.match(adresse):
            return adresse
        print("  Adresse invalide.\n")


def demander_mot_de_passe() -> str:
    """Saisie masquee, puis confirmation.

    LA CONFIRMATION N'EST PAS DU CONFORT : la saisie etant invisible,
    une faute de frappe ne se decouvrirait qu'a la premiere connexion,
    sur un compte qu'on ne pourrait plus recuperer autrement qu'en
    relancant ce script.
    """
    while True:
        secret = getpass.getpass("Mot de passe (invisible) : ")
        if len(secret) < LONGUEUR_MINIMALE:
            print(f"  {LONGUEUR_MINIMALE} caracteres au minimum.\n")
            continue
        if secret != getpass.getpass("Confirmez le mot de passe : "):
            print("  Les deux saisies different.\n")
            continue
        return secret


def main() -> int:
    print()
    print("  Creation d'un compte d'administration — ChatDocs OHADA")
    print(f"  Base : {parametres.database_url.split('@')[-1]}")
    print()

    adresse = demander_email()

    with FabriqueSession() as session:
        existant = session.execute(
            text("SELECT id, role FROM utilisateur WHERE email = :e"),
            {"e": adresse},
        ).mappings().first()

        if existant:
            if existant["role"] == "admin":
                print(f"\n  Ce compte est deja administrateur (#{existant['id']}).")
                return 0
            reponse = input(
                f"\n  Ce compte existe (#{existant['id']}, role "
                f"« {existant['role']} »).\n"
                "  Le promouvoir administrateur, sans toucher a son mot de "
                "passe ? [o/N] "
            )
            if reponse.strip().lower() not in {"o", "oui"}:
                print("  Rien n'a ete modifie.")
                return 1
            session.execute(
                text("UPDATE utilisateur SET role = 'admin' WHERE id = :id"),
                {"id": existant["id"]},
            )
            session.commit()
            print(f"\n  Compte #{existant['id']} promu administrateur.")
            return 0

        secret = demander_mot_de_passe()

        # cgu_version est renseignee : un compte cree ici a accepte les
        # conditions par le fait meme d'etre cree par l'exploitant. Le
        # laisser vide ferait redemander l'acceptation a la connexion.
        identifiant = session.execute(
            text(
                """
                INSERT INTO utilisateur
                    (email, mot_de_passe_hash, role, plan, quota_restant,
                     quota_reinit_le, cgu_version, cgu_acceptees_le)
                VALUES
                    (:e, :h, 'admin', 'gratuit', 10, CURRENT_DATE,
                     :cgu, now())
                RETURNING id
                """
            ),
            {"e": adresse, "h": hacher(secret), "cgu": parametres.version_cgu},
        ).scalar()
        session.commit()

    print(f"\n  Compte administrateur cree : {adresse} (#{identifiant})")
    print("  Connectez-vous par e-mail et mot de passe sur /connexion.")
    print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n  Interrompu. Rien n'a ete modifie.")
        raise SystemExit(1)
    except EOFError:
        # Entree fermee : le script a ete lance sans terminal, par une
        # redirection ou une tache automatisee. Une trace Python y
        # ressemblerait a un plantage alors que rien n'a echoue — et
        # surtout, le mot de passe DOIT etre saisi a la main. Ce script
        # n'a pas de mode non interactif, et c'est voulu : le passer en
        # argument le laisserait dans l'historique du terminal.
        print(
            "\n  Ce script demande une saisie : lancez-le depuis un "
            "terminal.\n  Rien n'a ete modifie."
        )
        raise SystemExit(1)
