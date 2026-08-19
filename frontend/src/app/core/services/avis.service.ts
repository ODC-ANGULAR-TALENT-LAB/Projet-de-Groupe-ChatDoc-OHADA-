import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService, ErreurApi } from './api.service';

export interface Avis {
  note: number;
  commentaire: string | null;
  cree_le: string;
  /** Renseigné seulement si l'avis a été revu après coup. */
  modifie_le: string | null;
}

export interface AvisAdministration extends Avis {
  utilisateur_id: number;
  email: string;
  prenom: string | null;
}

export interface SyntheseAvis {
  nombre: number;
  moyenne: number | null;
  /** Nombre d'avis par note, de 1 à 5. */
  repartition: Record<number, number>;
  avis: AvisAdministration[];
}

/**
 * Avis des utilisateurs sur l'application.
 *
 * UN SEUL AVIS PAR COMPTE, MODIFIABLE. `enregistrer` sert à déposer
 * comme à réviser : l'interface n'a pas à savoir si un avis existe déjà
 * avant d'agir, exactement comme pour les favoris.
 *
 * L'AVIS PORTE SUR LE PRODUIT, pas sur une réponse donnée. Juger une
 * réponse demanderait de la rattacher à sa question et à ses citations
 * — un autre objet, qui reste à construire si le besoin apparaît.
 */
@Injectable({ providedIn: 'root' })
export class AvisService {
  private readonly api = inject(ApiService);

  async mien(): Promise<Avis | null> {
    return firstValueFrom(this.api.get<Avis | null>('/moi/avis'));
  }

  async enregistrer(note: number, commentaire: string | null): Promise<Avis> {
    return firstValueFrom(
      this.api.put<Avis>('/moi/avis', { note, commentaire }),
    );
  }

  async retirer(): Promise<void> {
    await firstValueFrom(this.api.delete<void>('/moi/avis'));
  }

  /** Réservé à l'administration : le serveur refuse aux autres (403). */
  async synthese(): Promise<SyntheseAvis> {
    return firstValueFrom(this.api.get<SyntheseAvis>('/admin/avis'));
  }

  message(erreur: unknown): string {
    if (erreur instanceof ErreurApi) return erreur.message;
    return "L'enregistrement de votre avis a échoué.";
  }
}
