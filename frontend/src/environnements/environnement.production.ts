/**
 * Configuration de production.
 *
 * Substitué à environnement.ts au build de production
 * (fileReplacements dans angular.json).
 *
 * `urlApi` doit pointer vers l'API déployée, en HTTPS. Ce domaine doit
 * aussi figurer dans ORIGINES_AUTORISEES côté serveur, sinon le
 * navigateur bloquera les appels sans message explicite.
 */
export const environnement = {
  production: true,
  urlApi: 'https://api.chatdocs-ohada.example',
  googleClientId:
    '1027327411066-5ediopqgl5na872p156iucve9elurbos.apps.googleusercontent.com',
};
