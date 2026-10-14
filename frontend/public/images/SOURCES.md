# Provenance des images

Le même principe que pour le corpus : **rien n'entre sans sa source.**
Une image dont on ne sait plus d'où elle vient est un risque juridique
qu'on découvre au mauvais moment.

| Fichier | Source | Licence | Récupérée le |
|---|---|---|---|
| `reunion-lagos.webp` | [Pexels — *Diverse Team in Business Meeting at Lagos Office*](https://www.pexels.com/photo/diverse-team-in-business-meeting-at-lagos-office-30677714/) | [Licence Pexels](https://www.pexels.com/license/) — usage commercial autorisé, attribution non requise | 2026-10-14 |

## Traitement appliqué

`reunion-lagos.webp` est recadrée au format du hero (2,32:1, bande
prise à 180 px du haut de l'original 2400×1600 pour garder les visages),
ramenée à 1600 px de large, **assombrie** (luminosité × 0,42, saturation
× 0,8, puis 18 % de bleu nuit `#1b2a4a`) et convertie en WebP (qualité
74) — **25 Ko**.

L'ORIGINAL EST CONSERVÉ dans `Docs/images/reunion-lagos-original.jpg`
(2400×1600, 277 Ko), hors de `public/` pour ne pas être livré avec le
site. C'est lui qu'il faut reprendre pour un autre recadrage ou un autre
traitement : retravailler le WebP, déjà compressé et assombri,
dégraderait l'image à chaque passe.

L'ASSOMBRISSEMENT N'EST PAS UN EFFET DE STYLE. L'original est une pièce
blanche baignée de lumière : posée telle quelle sous le voile, elle
faisait tomber le contraste au pire à 1,4:1 sur les liens du menu et à
2,4:1 sur le titre. Après traitement, le pire cas mesuré est 4,6:1
(« Méthodologie ») et 9,5:1 pour le titre. Le voile, réglé pour l'image
précédente, a ensuite été allégé d'environ 40 % pour laisser voir la
scène ; les liens du menu sont passés de `--sur-nuit-faible` à
`--sur-nuit` pour rester lisibles (7,5:1 au pire). Le pire cas de toute
la zone est désormais 4,65:1.

Elle remplace `cabinet.webp` (consultation dans un cabinet, Pexels
8112152) : la page d'accueil d'un outil de droit OHADA doit montrer son
public — des professionnels africains, dans un décor d'Afrique de
l'Ouest.

Le recadrage est fait ici plutôt que laissé au navigateur : sinon le
point de coupe varie avec la largeur de l'écran, et c'est justement le
sujet — la personne assise en face — qui disparaît en premier.

## Si l'image doit être remplacée

1. Vérifier que la licence de la nouvelle autorise l'usage commercial.
2. La déposer dans ce dossier, ajouter sa ligne au tableau ci-dessus.
3. Adapter `object-position` dans `landing.page.scss` sur le sujet de
   la nouvelle image, pour que le recadrage des écrans étroits le garde.
4. Vérifier le contraste du titre par-dessus — c'est la seule contrainte
   non négociable.
