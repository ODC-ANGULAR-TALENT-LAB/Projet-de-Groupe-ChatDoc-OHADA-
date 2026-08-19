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
  // Dockerfile et celui du README.
  //
  // 127.0.0.1 ET NON `localhost`, ET C'EST MESURÉ. Uvicorn écoute par
  // défaut sur 127.0.0.1, en IPv4 seulement. Or sous Windows
  // `localhost` résout d'abord en IPv6 (::1) : le navigateur tente
  // cette adresse, attend le refus, puis retombe sur IPv4.
  //
  //   via localhost  : 0,30 s dont 0,23 s à établir la connexion
  //   via 127.0.0.1  : 0,08 s dont 0,02 s
  //
  // Ce délai se paie sur CHAQUE appel, pas seulement au chargement —
  // d'où une application qui paraît lente partout sans qu'aucune
  // requête ne soit lente en elle-même.
  urlApi: 'http://127.0.0.1:8000',
  // Client ID Google : public par nature, il identifie l'application
  // auprès de Google. Le code secret, lui, reste côté serveur et n'a
  // rien à faire ici.
  googleClientId:
    '1027327411066-5ediopqgl5na872p156iucve9elurbos.apps.googleusercontent.com',
};
