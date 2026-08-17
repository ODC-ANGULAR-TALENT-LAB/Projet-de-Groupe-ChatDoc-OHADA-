import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from '../services/auth.service';

/**
 * Ajoute l'en-tête Authorization à chaque appel sortant.
 *
 * Les routes du corpus (/textes, /articles, /recherche) sont publiques
 * et fonctionnent sans jeton : l'en-tête est simplement ignoré.
 */
export const jwtInterceptor: HttpInterceptorFn = (requete, suivant) => {
  const jeton = inject(AuthService).jeton();
  if (!jeton) return suivant(requete);

  return suivant(
    requete.clone({ setHeaders: { Authorization: `Bearer ${jeton}` } }),
  );
};
