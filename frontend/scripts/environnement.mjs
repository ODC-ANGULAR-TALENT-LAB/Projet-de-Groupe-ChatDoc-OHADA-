/**
 * Écrit la configuration de production à partir des variables
 * d'environnement, juste avant le build.
 *
 * POURQUOI CE SCRIPT EXISTE. `environnement.production.ts` est
 * substitué à `environnement.ts` au build (fileReplacements), et il
 * était COMMITÉ AVEC L'URL DE L'API ÉCRITE EN DUR. Changer d'API
 * demandait donc de modifier le code et de committer — ce qui rend un
 * hébergeur comme Vercel inutilisable tel quel : on ne peut pas avoir
 * une préproduction et une production sur le même dépôt, et chaque
 * changement de domaine devient un commit.
 *
 * Ici, l'URL vient des variables du projet Vercel. Le fichier commité
 * reste le DÉFAUT : sans variable définie, il n'est pas touché, et un
 * build local se comporte exactement comme avant.
 *
 * CE QUI EST ÉCRIT ICI EST PUBLIC. Une application web n'a pas de
 * secret : tout ce que le navigateur reçoit est lisible. `URL_API` et
 * `GOOGLE_CLIENT_ID` sont des identifiants publics par nature — le
 * client ID Google sert à identifier l'application, pas à l'authentifier.
 * Aucune clé d'API ne doit jamais passer par ici.
 */

import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ici = dirname(fileURLToPath(import.meta.url));
const cible = join(ici, '..', 'src', 'environnements', 'environnement.production.ts');

const urlApi = process.env.URL_API;
const clientGoogle = process.env.GOOGLE_CLIENT_ID;

if (!urlApi) {
  console.log(
    "  URL_API non définie : environnement.production.ts est laissé tel quel.\n" +
      '  (attendu en local ; sur Vercel, définissez-la dans les variables du projet)',
  );
  process.exit(0);
}

// Une URL avec une barre oblique finale produirait `https://api//chat` :
// deux barres, que certains hébergeurs refusent et que d'autres
// redirigent — ce qui casse silencieusement le preflight CORS.
const url = urlApi.replace(/\/+$/, '');

if (!url.startsWith('https://')) {
  console.error(
    `  URL_API doit être en HTTPS : « ${url} » refusé.\n` +
      "  Un site servi en HTTPS ne peut pas appeler une API en clair :\n" +
      '  le navigateur bloque la requête sans message explicite.',
  );
  process.exit(1);
}

const contenu = `/**
 * Configuration de production — FICHIER GÉNÉRÉ.
 *
 * Écrit par scripts/environnement.mjs à partir des variables
 * d'environnement du build. Ne pas modifier à la main : la prochaine
 * construction écraserait le changement.
 *
 * Pour changer d'API, modifiez URL_API dans les variables du projet
 * chez l'hébergeur, puis relancez le déploiement.
 */
export const environnement = {
  production: true,
  urlApi: '${url}',
  googleClientId:
    '${clientGoogle ?? '1027327411066-5ediopqgl5na872p156iucve9elurbos.apps.googleusercontent.com'}',
};
`;

writeFileSync(cible, contenu, 'utf8');
console.log(`  Configuration de production écrite : urlApi = ${url}`);
