# Provenance des images

Le même principe que pour le corpus : **rien n'entre sans sa source.**
Une image dont on ne sait plus d'où elle vient est un risque juridique
qu'on découvre au mauvais moment.

| Fichier | Source | Licence | Récupérée le |
|---|---|---|---|
| `cabinet.webp` | [Pexels — *People at Lawyers Office*](https://www.pexels.com/photo/people-at-lawyers-office-8112152/) | [Licence Pexels](https://www.pexels.com/license/) — usage commercial autorisé, attribution non requise | 2026-08-17 |

## Traitement appliqué

`cabinet.webp` est recadrée au format du hero (2,32:1), ramenée à
1600 px de large et convertie en WebP (qualité 72) — **35 Ko**.

Le recadrage est fait ici plutôt que laissé au navigateur : sinon le
point de coupe varie avec la largeur de l'écran, et c'est justement le
sujet — la personne assise en face — qui disparaît en premier.

## Si l'image doit être remplacée

1. Vérifier que la licence de la nouvelle autorise l'usage commercial.
2. La déposer dans ce dossier, ajouter sa ligne au tableau ci-dessus.
3. Adapter `object-position` dans `landing.page.scss` : le voile est
   dense à gauche, l'image doit donc porter son sujet à droite.
4. Vérifier le contraste du titre par-dessus — c'est la seule contrainte
   non négociable.
