import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService, ErreurApi } from './api.service';

export type Role = 'utilisateur' | 'juriste' | 'admin';

export interface CompteAdmin {
  id: number;
  email: string;
  prenom: string | null;
  role: Role;
  plan: string;
  quota_restant: number;
  plan_echeance: string | null;
  connexion_google: boolean;
  /** Meilleure approximation de la date d'inscription : la table ne
   *  porte pas de date de création. */
  cgu_acceptees_le: string | null;
}

export interface TableauDeBord {
  comptes: number;
  /** Une clé absente vaut « aucun compte », pas zéro déclaré : le type
   *  doit le dire, sinon TypeScript croit la garde `?? 0` inutile et
   *  invite à la retirer — ce qui afficherait un blanc à la place. */
  comptes_par_role: Record<string, number | undefined>;
  comptes_google: number;
  abonnes_payants: number;
  abonnes_par_forfait: Record<string, number | undefined>;
  revenu_mensuel_fcfa: number;
  demandes_en_attente: number;
  avis_nombre: number;
  avis_moyenne: number | null;
  textes: number;
  articles: number;
  articles_vectorises: number;
}

/**
 * Administration de l'application.
 *
 * DISTINCT DE L'ESPACE JURISTE, et la séparation est volontaire. Le
 * juriste tient le corpus : il dépose, relit et valide des textes, et
 * il en répond. L'administrateur tient le service : comptes, rôles,
 * abonnements, avis. Un juriste ne distribue pas les droits — sinon
 * quiconque obtient le droit de valider un texte peut se l'octroyer à
 * d'autres, et la chaîne de responsabilité inscrite dans la table de
 * provenance ne veut plus rien dire.
 *
 * CE SERVICE NE LIT AUCUNE DONNÉE DE TRAVAIL. Ni conversations, ni
 * favoris, ni annotations : administrer le service ne donne aucune
 * légitimité à lire des notes prises sur des dossiers clients. Aucune
 * route du serveur ne les expose, et rien ici ne cherche à les
 * atteindre.
 */
@Injectable({ providedIn: 'root' })
export class AdministrationService {
  private readonly api = inject(ApiService);

  async tableauDeBord(): Promise<TableauDeBord> {
    return firstValueFrom(this.api.get<TableauDeBord>('/admin/tableau-de-bord'));
  }

  async comptes(): Promise<CompteAdmin[]> {
    return firstValueFrom(this.api.get<CompteAdmin[]>('/admin/utilisateurs'));
  }

  /**
   * Attribue un rôle.
   *
   * Le serveur refuse (409) qu'un administrateur se retire à lui-même
   * le dernier rôle d'administrateur : ce serait fermer la porte à clef
   * de l'intérieur. L'interface se contente de rapporter ce refus.
   */
  async changerRole(id: number, role: Role): Promise<CompteAdmin> {
    return firstValueFrom(
      this.api.patch<CompteAdmin>(`/admin/utilisateurs/${id}/role`, { role }),
    );
  }

  message(erreur: unknown): string {
    if (erreur instanceof ErreurApi) return erreur.message;
    return "L'opération a échoué.";
  }
}
