"""Applique les migrations de db/ dans l'ordre.

    python scripts/appliquer_migrations.py

POURQUOI CE SCRIPT EXISTE. docker-compose ne monte que `db/init/`, et
les scripts qui s'y trouvent ne sont joues QU'UNE FOIS, a la creation
du volume. Les migrations `db/NN_*.sql` ne le sont donc jamais
automatiquement : un depot fraichement clone obtient le schema initial
et rien d'autre. L'application y perd la connexion Google, les depots,
les signalements, les favoris, les conditions d'utilisation, le profil,
les avis, les forfaits et la suspension des comptes — soit a peu pres
tout ce qui a ete construit depuis.

Le symptome est deroutant : l'API demarre, puis echoue au premier appel
avec une colonne inconnue.

POURQUOI PAS DANS db/init/. Les fichiers de ce dossier ne rejouent pas
sur un volume existant : y deplacer les migrations les rendrait
inapplicables a toute base deja creee — c'est-a-dire a toutes celles
qui existent.

IDEMPOTENT. Les migrations sont ecrites en `IF NOT EXISTS` /
`ON CONFLICT DO NOTHING` ; relancer ce script sur une base a jour ne
fait rien. C'est ce qui permet de l'executer sans se demander ou l'on
en est.
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "backend"))

from sqlalchemy import text  # noqa: E402

from app.config import parametres  # noqa: E402
from app.db import moteur  # noqa: E402


def migrations() -> list[Path]:
    """Les fichiers de db/, dans l'ordre de leur numero.

    `db/init/` n'y figure pas : il est traite a part, car il n'est PAS
    idempotent (voir `schema_initial_manquant`).
    """
    return sorted(
        (chemin for chemin in (RACINE / "db").glob("*.sql")),
        key=lambda p: p.name,
    )


def schema_initial_manquant() -> bool:
    """La base est-elle vierge ?

    POURQUOI CETTE DETECTION. `db/init/01_schema.sql` n'est joue que par
    docker-compose, a la creation du volume. Sur une base hebergee —
    Neon, Supabase, le Postgres d'un PaaS — personne ne le joue, et les
    migrations echouent toutes en cascade sur des tables inexistantes.

    Ce fichier n'est PAS idempotent : ses `CREATE TABLE` n'ont pas de
    garde `IF NOT EXISTS`, et le rejouer sur une base peuplee echouerait.
    On ne l'applique donc que si la table `texte` est absente, ce qui ne
    peut signifier qu'une chose : la base n'a jamais ete initialisee.
    """
    with moteur.connect() as connexion:
        return (
            connexion.execute(
                text("SELECT to_regclass('public.texte')")
            ).scalar()
            is None
        )


def appliquer_schema_initial() -> bool:
    fichiers = sorted((RACINE / "db" / "init").glob("*.sql"), key=lambda p: p.name)
    for chemin in fichiers:
        try:
            with moteur.begin() as connexion:
                connexion.execute(text(chemin.read_text(encoding="utf-8")))
            print(f"    ok       init/{chemin.name}")
        except Exception as erreur:  # noqa: BLE001
            print(f"    ECHEC    init/{chemin.name}")
            print(f"             {str(erreur).strip().splitlines()[0][:150]}")
            return False
    return True


# Identifiant arbitraire mais STABLE du verrou : deux processus ne se
# coordonnent que s'ils demandent la meme cle. Ne pas la changer.
CLE_VERROU = 8_140_2026


def main() -> int:
    fichiers = migrations()
    if not fichiers:
        print("  Aucune migration trouvée dans db/.")
        return 1

    print()
    print(f"  Base : {parametres.database_url.split('@')[-1]}")

    # UN SEUL PROCESSUS A LA FOIS. Depuis que ce script tourne au
    # demarrage du conteneur, plusieurs instances peuvent l'executer en
    # meme temps : un redeploiement recouvre l'ancienne instance, et
    # l'hebergeur peut relancer un conteneur tombe pendant que l'autre
    # migre encore. Deux `CREATE INDEX` concurrents sur la meme table
    # se bloquent mutuellement jusqu'au deadlock, et la panne est
    # intermittente — donc penible a reproduire.
    #
    # Le verrou est pris sur une connexion DEDIEE, gardee ouverte : un
    # verrou de session disparait avec sa connexion, et le rendre sur
    # une connexion du pool le libererait au premier recyclage.
    with moteur.connect() as verrou:
        verrou.execute(text("SELECT pg_advisory_lock(:cle)"), {"cle": CLE_VERROU})
        try:
            return _appliquer(fichiers)
        finally:
            verrou.execute(
                text("SELECT pg_advisory_unlock(:cle)"), {"cle": CLE_VERROU}
            )


def _appliquer(fichiers: list[Path]) -> int:
    """Le travail lui-meme, une fois le verrou obtenu."""
    # Base vierge — typiquement une base hebergee fraichement creee.
    # Sans cette etape, les quatorze migrations echoueraient toutes en
    # cascade sur des tables inexistantes, et le diagnostic serait noye
    # dans quatorze messages identiques.
    if schema_initial_manquant():
        print("  Base vierge : application du schéma initial.\n")
        if not appliquer_schema_initial():
            print("\n  Le schéma initial a échoué : on s'arrête là.")
            return 1
        print()

    print(f"  {len(fichiers)} migration(s) à appliquer\n")

    echecs = 0
    for chemin in fichiers:
        sql = chemin.read_text(encoding="utf-8")
        try:
            # Une transaction PAR FICHIER : une migration qui echoue au
            # milieu ne doit pas laisser un schema a moitie modifie, et
            # ne doit pas empecher les suivantes d'etre tentees.
            with moteur.begin() as connexion:
                connexion.execute(text(sql))
            print(f"    ok       {chemin.name}")
        except Exception as erreur:  # noqa: BLE001 - on veut le diagnostic brut
            echecs += 1
            premiere_ligne = str(erreur).strip().splitlines()[0]
            print(f"    ECHEC    {chemin.name}")
            print(f"             {premiere_ligne[:150]}")

    print()
    if echecs:
        print(f"  {echecs} migration(s) en échec. Le schéma est incomplet.")
        return 1

    print("  Schéma à jour.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
