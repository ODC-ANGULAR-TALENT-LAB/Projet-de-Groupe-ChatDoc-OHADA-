import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * Ajoute l'en-tête Authorization à chaque appel sortant, et met fin à la
 * session dès que le serveur la rejette.
 *
 * Les routes du corpus (/textes, /articles, /recherche) sont publiques
 * et fonctionnent sans jeton : l'en-tête est simplement ignoré.
 *
 * POURQUOI FERMER LA SESSION ICI. `connecte()` ne regarde que la
 * PRÉSENCE du jeton, jamais sa validité — il ne peut pas faire
 * autrement, la signature se vérifie côté serveur. Or le jeton expire au
 * bout de trente minutes. Sans cette gestion du 401, l'application
 * restait dans un état où l'interface affiche un utilisateur connecté —
 * navigation, bouton « Mettre en favori », tout est là — pendant que
 * chaque écriture est rejetée. L'utilisateur clique, rien ne s'enregistre,
 * et rien ne lui dit pourquoi ni comment en sortir : le jeton mort reste
 * en place jusqu'à une déconnexion manuelle.
 *
 * ON NE FERME QUE CE QU'ON CROYAIT OUVERT. Le 401 n'entraîne une
 * déconnexion que si la requête PORTAIT un jeton. Un mot de passe erroné
 * sur /auth/connexion répond 401 lui aussi ; le traiter de la même façon
 * ferait rebondir l'utilisateur depuis la page de connexion vers
 * elle-même, en effaçant le message d'erreur qu'il devait lire.
 */
export const jwtInterceptor: HttpInterceptorFn = (requete, suivant) => {
  const auth = inject(AuthService);
  const routeur = inject(Router);

  const jeton = auth.jeton();
  if (!jeton) return suivant(requete);

  return suivant(
    requete.clone({ setHeaders: { Authorization: `Bearer ${jeton}` } }),
  ).pipe(
    catchError((erreur: unknown) => {
      if (erreur instanceof HttpErrorResponse && erreur.status === 401) {
        // `false` : on navigue nous-mêmes juste après, en signalant
        // l'expiration. Laisser deconnexion() rediriger aussi ferait
        // deux navigations, et la nôtre perdrait le message.
        auth.deconnexion(false);
        void routeur.navigate(['/connexion'], {
          queryParams: { session: 'expiree' },
          replaceUrl: true,
        });
      }
      return throwError(() => erreur);
    }),
  );
};
