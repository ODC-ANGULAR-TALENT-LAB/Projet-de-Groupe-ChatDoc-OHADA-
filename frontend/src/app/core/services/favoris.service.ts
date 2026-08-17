import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService, ErreurApi } from './api.service';

export interface Favori {
  article_id: number;
  sigle: string;
  numero: string;
  chemin: string;
  apercu: string;
  note: string | null;
  cree_le: string;
  modifie_le: string | null;
  version_vue: string | null;
  version_courante: string;
  /** Le texte a été révisé depuis la mise en favori. */
  texte_revise: boolean;
  /** Cet article précis a été abrogé. Plus grave que le précédent. */
  article_abroge: boolean;
}

export interface AlerteVeille {
  article_id: number;
  sigle: string;
  numero: string;
  version_vue: string | null;
  version_courante: string;
  motif: 'texte_revise' | 'article_abroge';
}

/**
 * Favoris, annotations personnelles et veille ciblée.
 *
 * LE NOMBRE D'ALERTES EST UN SIGNAL PARTAGÉ. La pastille de la
 * navigation et la page de veille lisent la même valeur : deux
 * compteurs séparés finiraient par se contredire, et un utilisateur qui
 * voit « 3 » dans la barre et rien sur la page cesse de faire confiance
 * aux deux.
 */
@Injectable({ providedIn: 'root' })
export class FavorisService {
  private readonly api = inject(ApiService);

  readonly alertes = signal<AlerteVeille[]>([]);

  async lister(): Promise<Favori[]> {
    return firstValueFrom(this.api.get<Favori[]>('/favoris'));
  }

  async etat(articleId: number): Promise<Favori | null> {
    return firstValueFrom(this.api.get<Favori | null>(`/favoris/${articleId}`));
  }

  async enregistrer(articleId: number, note: string | null): Promise<Favori> {
    const favori = await firstValueFrom(
      this.api.put<Favori>(`/favoris/${articleId}`, { note }),
    );
    void this.rafraichirAlertes();
    return favori;
  }

  async retirer(articleId: number): Promise<void> {
    await firstValueFrom(this.api.delete<void>(`/favoris/${articleId}`));
    void this.rafraichirAlertes();
  }

  /**
   * Recharge les alertes de veille.
   *
   * Échoue en silence : un utilisateur déconnecté n'a pas d'alertes, et
   * afficher une erreur pour cela ferait du bruit sans rien apprendre.
   */
  async rafraichirAlertes(): Promise<void> {
    try {
      this.alertes.set(
        await firstValueFrom(this.api.get<AlerteVeille[]>('/veille')),
      );
    } catch {
      this.alertes.set([]);
    }
  }

  message(erreur: unknown): string {
    if (erreur instanceof ErreurApi) return erreur.message;
    return "L'enregistrement a échoué.";
  }
}
