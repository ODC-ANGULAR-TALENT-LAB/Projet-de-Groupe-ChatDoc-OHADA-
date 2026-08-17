/**
 * Configuration d'exécution.
 *
 * Phase H : la mise en production remplacera ce fichier par un
 * environnement de production (fileReplacements dans angular.json)
 * pointant vers l'API déployée.
 */
export const environnement = {
  production: false,
  // 8000 : le port de `uvicorn app.main:app --reload`, celui du
  // Dockerfile et celui du README. Ce fichier indiquait 8001, où rien
  // n'écoute — toutes les requêtes partaient dans le vide, et
  // l'application semblait cassée alors que l'API répondait très bien.
  urlApi: 'http://localhost:8000',
  // Client ID Google : public par nature, il identifie l'application
  // auprès de Google. Le code secret, lui, reste côté serveur et n'a
  // rien à faire ici.
  googleClientId:
    '1027327411066-5ediopqgl5na872p156iucve9elurbos.apps.googleusercontent.com',
};
