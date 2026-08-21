#!/bin/sh
# Demarrage de l'API dans le conteneur : migrations, puis serveur.
#
# POURQUOI LES MIGRATIONS ICI. Sur un hebergeur, personne ne joue
# `db/init/` : ce dossier n'est monte que par docker-compose, en local.
# Une base hebergee fraichement creee est donc VIDE, et le symptome est
# deroutant — l'API demarre normalement, puis echoue au premier appel
# sur une table inconnue.
#
# Le script est idempotent (voir appliquer_migrations.py) : le rejouer
# a chaque demarrage ne coute qu'une poignee de requetes, et garantit
# que le schema suit le code sans intervention manuelle.

set -e

cd /app/backend

# ON S'ARRETE SI LES MIGRATIONS ECHOUENT. `set -e` fait tomber le
# conteneur, l'hebergeur marque le deploiement en echec et GARDE LA
# VERSION PRECEDENTE EN LIGNE. Demarrer malgre tout mettrait en service
# un code neuf sur un schema ancien : les pannes arriveraient plus tard,
# une par une, chez les utilisateurs.
python scripts/appliquer_migrations.py

# `exec` : uvicorn REMPLACE ce shell et devient le PID 1. Sans cela, le
# SIGTERM envoye par l'hebergeur a l'arret irait au shell, qui ne le
# transmettrait pas — l'arret se ferait par SIGKILL apres expiration du
# delai, en coupant les reponses en cours.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
