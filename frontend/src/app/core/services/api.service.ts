import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environnement } from '../../../environnements/environnement';

/** Erreur métier remontée à l'interface, déjà traduite en français. */
export class ErreurApi extends Error {
  constructor(
    message: string,
    readonly statut: number,
  ) {
    super(message);
  }
}

/**
 * Point de passage unique vers l'API.
 *
 * Le frontend ne contient aucune logique juridique et n'appelle jamais
 * le fournisseur LLM : tout transite par le backend, où vivent la clé
 * d'API, le contrôle du quota et la validation des citations.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environnement.urlApi;

  get<T>(chemin: string, parametres?: Record<string, string | number>): Observable<T> {
    return this.http
      .get<T>(`${this.base}${chemin}`, { params: parametres })
      .pipe(catchError((erreur) => this.traduire(erreur)));
  }

  post<T>(chemin: string, corps: unknown): Observable<T> {
    return this.http
      .post<T>(`${this.base}${chemin}`, corps)
      .pipe(catchError((erreur) => this.traduire(erreur)));
  }

  put<T>(chemin: string, corps: unknown): Observable<T> {
    return this.http
      .put<T>(`${this.base}${chemin}`, corps)
      .pipe(catchError((erreur) => this.traduire(erreur)));
  }

  delete<T>(chemin: string): Observable<T> {
    return this.http
      .delete<T>(`${this.base}${chemin}`)
      .pipe(catchError((erreur) => this.traduire(erreur)));
  }

  /**
   * Traduit les codes du contrat d'API en messages lisibles.
   *
   * 402 n'est pas une panne mais une limite du plan, et 503 n'est pas
   * un refus de l'assistant mais une indisponibilité : les confondre
   * donnerait à l'utilisateur une idée fausse de ce qui se passe.
   */
  private traduire(erreur: HttpErrorResponse) {
    const messages: Record<number, string> = {
      0: "Impossible de joindre le service. Vérifiez votre connexion.",
      401: 'Votre session a expiré. Reconnectez-vous.',
      402: 'Votre quota mensuel est épuisé.',
      404: 'Ressource introuvable.',
      409: 'Cet e-mail est déjà inscrit.',
      503: "Le moteur de recherche est momentanément indisponible.",
    };
    const message =
      messages[erreur.status] ??
      erreur.error?.detail ??
      "Une erreur est survenue.";
    return throwError(() => new ErreurApi(message, erreur.status));
  }
}
