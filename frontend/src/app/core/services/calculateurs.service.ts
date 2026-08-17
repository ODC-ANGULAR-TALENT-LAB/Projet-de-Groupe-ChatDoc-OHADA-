import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService, ErreurApi } from './api.service';

/**
 * Un calculateur proposé, et l'état de sa base légale.
 *
 * `disponible` dit si l'article qui fonde le barème est réellement dans
 * le corpus. Proposer un calculateur sans base légale enverrait
 * l'utilisateur vers un refus après qu'il a saisi ses montants.
 */
export interface Calculateur {
  cle: string;
  libelle: string;
  description: string;
  sigle: string;
  numero_article: string;
  disponible: boolean;
  indisponible_parce_que: string | null;
}

/** L'article qui fonde une ligne du résultat, avec son extrait officiel. */
export interface BaseLegale {
  libelle: string;
  valeur: string;
  sigle: string;
  numero: string;
  chemin: string;
  extrait: string;
}

export interface LigneResultat {
  libelle: string;
  montant: string;
  base_legale?: BaseLegale;
}

export interface ResultatCalcul {
  intitule: string;
  lignes: LigneResultat[];
  resultat: { libelle: string; montant: string };
}

@Injectable({ providedIn: 'root' })
export class CalculateursService {
  private readonly api = inject(ApiService);

  async lister(): Promise<Calculateur[]> {
    return firstValueFrom(this.api.get<Calculateur[]>('/calculateurs'));
  }

  async tva(montant: string, surTtc: boolean): Promise<ResultatCalcul> {
    return firstValueFrom(
      this.api.post<ResultatCalcul>('/calculateurs/tva', {
        montant,
        sur_ttc: surTtc,
      }),
    );
  }

  async impotSocietes(montant: string): Promise<ResultatCalcul> {
    return firstValueFrom(
      this.api.post<ResultatCalcul>('/calculateurs/is', { montant }),
    );
  }

  /**
   * Remonte le message du serveur tel quel.
   *
   * Un refus de calcul nomme l'article en cause — « l'article 128 ne
   * mentionne plus ce taux ». Le remplacer par « une erreur est
   * survenue » priverait le juriste de la seule information qui lui
   * permet d'agir.
   */
  message(erreur: unknown): string {
    if (erreur instanceof ErreurApi) return erreur.message;
    const detail = (erreur as { error?: { detail?: unknown } })?.error?.detail;
    if (typeof detail === 'string') return detail;
    return 'Le calcul a échoué.';
  }
}
