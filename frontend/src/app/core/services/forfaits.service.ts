import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService, ErreurApi } from './api.service';

export interface Forfait {
  code: string;
  libelle: string;
  prix_fcfa: number;
  credits: number;
  argumentaire: string;
  atouts: string[];
}

export interface Abonnement {
  forfait: Forfait;
  credits_restants: number;
  /** Dernier jour de validité du forfait payé. `null` sur le gratuit. */
  echeance: string | null;
  /** Code du forfait demandé, tant que l'administration ne l'a pas traité. */
  demande_en_attente: string | null;
  /** CamPay configuré côté serveur : sinon, règlement hors ligne. */
  paiement_mobile: boolean;
}

export interface Paiement {
  reference: string;
  statut: 'PENDING' | 'SUCCESSFUL' | 'FAILED';
  /** Code à composer si l'invite USSD n'apparaît pas d'elle-même. */
  code_ussd: string | null;
  operateur: string | null;
  /** Renseigné dès que le paiement aboutit. */
  abonnement: Abonnement | null;
}

export interface DemandeAbonnement {
  id: number;
  utilisateur_id: number;
  email: string;
  prenom: string | null;
  forfait_code: string;
  statut: 'en_attente' | 'validee' | 'refusee';
  demande_le: string;
  traite_le: string | null;
  reference: string | null;
  motif_refus: string | null;
}

/**
 * Forfaits et abonnement du compte.
 *
 * L'APPLICATION N'ENCAISSE PAS. Aucune méthode ici n'envoie de donnée
 * de paiement : `demander` dépose une intention, et c'est un
 * administrateur qui ouvre les crédits une fois le paiement constaté
 * hors application. Le service ne peut donc pas accorder un forfait
 * payant, quoi qu'on lui demande.
 */
@Injectable({ providedIn: 'root' })
export class ForfaitsService {
  private readonly api = inject(ApiService);

  /** Catalogue public : le prix se consulte sans compte. */
  async catalogue(): Promise<Forfait[]> {
    return firstValueFrom(this.api.get<Forfait[]>('/forfaits'));
  }

  async mien(): Promise<Abonnement> {
    return firstValueFrom(this.api.get<Abonnement>('/moi/abonnement'));
  }

  /**
   * Demande un forfait.
   *
   * Vers le gratuit, le changement est immédiat ; vers un forfait
   * payant, la réponse porte `demande_en_attente` et rien n'a encore
   * changé.
   */
  async demander(code: string): Promise<Abonnement> {
    return firstValueFrom(
      this.api.post<Abonnement>('/moi/abonnement', { forfait: code }),
    );
  }

  async annulerDemande(): Promise<void> {
    await firstValueFrom(this.api.delete<void>('/moi/abonnement/demande'));
  }

  /**
   * Lance un paiement Mobile Money.
   *
   * LE MONTANT N'EST PAS ENVOYÉ, et ce n'est pas un oubli : le serveur
   * le lit dans le catalogue à partir du code de forfait. L'envoyer
   * d'ici reviendrait à laisser le navigateur choisir son prix.
   *
   * Le numéro n'est pas un secret, c'est un identifiant. Le code
   * Mobile Money, lui, est saisi par l'abonné sur son téléphone et
   * n'entre jamais dans l'application.
   */
  async payer(forfait: string, telephone: string): Promise<Paiement> {
    return firstValueFrom(
      this.api.post<Paiement>('/moi/abonnement/payer', { forfait, telephone }),
    );
  }

  /**
   * Où en est le paiement en cours ?
   *
   * L'état est lu par le SERVEUR auprès de CamPay : cette réponse fait
   * foi, alors que rien de ce que le navigateur croit ne compte.
   */
  async suivrePaiement(): Promise<Paiement> {
    return firstValueFrom(this.api.get<Paiement>('/moi/abonnement/paiement'));
  }

  /** Réservé à l'administration : le serveur refuse aux autres (403). */
  async demandes(): Promise<DemandeAbonnement[]> {
    return firstValueFrom(this.api.get<DemandeAbonnement[]>('/admin/abonnements'));
  }

  async valider(id: number, reference: string, mois = 1): Promise<DemandeAbonnement> {
    return firstValueFrom(
      this.api.post<DemandeAbonnement>(`/admin/abonnements/${id}/valider`, {
        reference,
        mois,
      }),
    );
  }

  async refuser(id: number, motif: string): Promise<DemandeAbonnement> {
    return firstValueFrom(
      this.api.post<DemandeAbonnement>(`/admin/abonnements/${id}/refuser`, {
        motif,
      }),
    );
  }

  message(erreur: unknown): string {
    if (erreur instanceof ErreurApi) return erreur.message;
    return 'Le changement de forfait a échoué.';
  }
}
