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
# `--proxy-headers` : SANS LUI, TOUS LES UTILISATEURS PARTAGENT UNE SEULE
# ADRESSE. Le conteneur ne voit que le mandataire de l'hebergeur, donc
# `request.client.host` rend la meme valeur pour tout le monde. La
# limitation des tentatives de connexion (services/cadence.py) compterait
# alors les echecs de TOUS les visiteurs sur un compteur unique : cinq
# mots de passe rates, par cinq personnes differentes, et le service se
# fermerait a tout le monde.
#
# `--forwarded-allow-ips=*` accepte cet en-tete de n'importe quel
# appelant. C'est sur ICI, et seulement ici : le conteneur n'est
# joignable qu'a travers le mandataire de l'hebergeur, qui reecrit
# l'en-tete. Exposer ce port directement rendrait l'adresse falsifiable
# — et donc la limitation contournable.
exec uvicorn app.main:app \
    --host 0.0.0.0 --port "${PORT:-8000}" \
    --proxy-headers --forwarded-allow-ips='*'
