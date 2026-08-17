import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService, ErreurApi } from './api.service';

export interface Profil {
  email: string;
  prenom: string | null;
  photo_url: string | null;
  /** Deux lettres, calculées côté serveur. Servent d'avatar quand la
      photo ne charge pas — hors ligne, ou lien Google expiré. */
  initiales: string;

  role: string;
  plan: string;
  quota_restant: number;
  connexion_google: boolean;

  cgu_version: string | null;
  cgu_acceptees_le: string | null;

  preferences: Record<string, boolean | string>;
}

export interface ReglePreference {
  type: 'booleen' | 'texte';
  defaut: boolean | string;
  valeurs: string[] | null;
}

/**
 * Profil et préférences.
 *
 * LE PROFIL EST UN SIGNAL PARTAGÉ. Le prénom sert à la salutation de
 * l'accueil, l'avatar à la barre latérale, les préférences à plusieurs
 * pages. Trois copies finiraient par se contredire — un prénom changé
 * dans les paramètres et resté ancien dans la salutation.
 */
@Injectable({ providedIn: 'root' })
export class ProfilService {
  private readonly api = inject(ApiService);

  readonly profil = signal<Profil | null>(null);

  /** Le prénom, ou rien. Utilisé pour saluer. */
  readonly prenom = computed(() => this.profil()?.prenom ?? null);

  async charger(): Promise<void> {
    try {
      this.profil.set(await firstValueFrom(this.api.get<Profil>('/moi/profil')));
    } catch {
      // Un profil indisponible ne doit pas casser l'application : elle
      // fonctionne sans prénom ni avatar, simplement moins bien.
      this.profil.set(null);
    }
  }

  async catalogue(): Promise<Record<string, ReglePreference>> {
    return firstValueFrom(
      this.api.get<Record<string, ReglePreference>>(
        '/moi/preferences/catalogue',
      ),
    );
  }

  /**
   * Enregistre le profil.
   *
   * Les champs omis ne sont pas touchés : le serveur fusionne. Une page
   * qui n'affiche que les préférences ne doit pas effacer le prénom.
   */
  async enregistrer(modifications: {
    prenom?: string | null;
    preferences?: Record<string, boolean | string>;
  }): Promise<Profil> {
    const profil = await firstValueFrom(
      this.api.put<Profil>('/moi/profil', modifications),
    );
    this.profil.set(profil);
    return profil;
  }

  /** Remonte le message du serveur : il explique précisément le refus. */
  message(erreur: unknown): string {
    if (erreur instanceof ErreurApi) return erreur.message;
    const detail = (erreur as { error?: { detail?: unknown } })?.error?.detail;
    if (typeof detail === 'string') return detail;
    return "L'enregistrement a échoué.";
  }
}
