/**
 * Configuration d'exécution.
 *
 * Phase H : la mise en production remplacera ce fichier par un
 * environnement de production (fileReplacements dans angular.json)
 * pointant vers l'API déployée.
 */
export const environnement = {
  production: false,
  urlApi: 'http://localhost:8001',
  // Client ID Google : public par nature, il identifie l'application
  // auprès de Google. Le code secret, lui, reste côté serveur et n'a
  // rien à faire ici.
  googleClientId:
    '1027327411066-5ediopqgl5na872p156iucve9elurbos.apps.googleusercontent.com',
};
