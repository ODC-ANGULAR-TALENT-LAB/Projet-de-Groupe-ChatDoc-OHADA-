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

    `db/init/` est exclu : docker-compose s'en charge a la creation du
    volume, et le rejouer ici echouerait sur des tables existantes.
    """
    return sorted(
        (chemin for chemin in (RACINE / "db").glob("*.sql")),
        key=lambda p: p.name,
    )


def main() -> int:
    fichiers = migrations()
    if not fichiers:
        print("  Aucune migration trouvée dans db/.")
        return 1

    print()
    print(f"  Base : {parametres.database_url.split('@')[-1]}")
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
