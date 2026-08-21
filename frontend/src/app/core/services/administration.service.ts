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
  /** Renseigné = compte fermé : ni connexion, ni session déjà ouverte. */
  suspendu_le: string | null;
  suspendu_motif: string | null;
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

  // --- Catalogue des forfaits ---------------------------------------
  //
  // LA MARGE EST VÉRIFIÉE PAR LE SERVEUR, à l'écriture. Ce service ne
  // la recalcule pas et ne pré-valide rien : une règle appliquée à deux
  // endroits finit par diverger, et c'est celle du serveur qui compte.
  // Un refus revient en 422 avec un message qui dit quoi corriger.

  async forfaits(): Promise<ForfaitAdmin[]> {
    return firstValueFrom(this.api.get<ForfaitAdmin[]>('/admin/forfaits'));
  }

  async creerForfait(
    code: string,
    forfait: ForfaitEcriture,
  ): Promise<ForfaitAdmin> {
    return firstValueFrom(
      this.api.post<ForfaitAdmin>('/admin/forfaits', { code, ...forfait }),
    );
  }

  /** Le code n'est pas modifiable : il est inscrit sur chaque compte abonné. */
  async modifierForfait(
    code: string,
    forfait: ForfaitEcriture,
  ): Promise<ForfaitAdmin> {
    return firstValueFrom(
      this.api.put<ForfaitAdmin>(`/admin/forfaits/${code}`, forfait),
    );
  }

  // --- Registre des signalements -------------------------------------

  async signalements(): Promise<Signalement[]> {
    return firstValueFrom(this.api.get<Signalement[]>('/admin/signalements'));
  }

  /**
   * Clôt un signalement.
   *
   * `traite` quand quelque chose a été corrigé, `ecarte` quand le
   * signalement était infondé — ce sont les deux seuls statuts que la
   * contrainte SQL accepte. La nuance vit dans `correction`, exigée.
   */
  async traiterSignalement(
    id: number,
    statut: 'traite' | 'ecarte',
    correction: string,
  ): Promise<Signalement> {
    return firstValueFrom(
      this.api.post<Signalement>(`/admin/signalements/${id}/traiter`, {
        statut,
        correction,
      }),
    );
  }

  /**
   * Ferme l'accès sans rien effacer.
   *
   * LE MOTIF EST OBLIGATOIRE côté serveur : une suspension sans raison
   * rend toute réactivation arbitraire.
   */
  async suspendre(id: number, motif: string): Promise<CompteAdmin> {
    return firstValueFrom(
      this.api.post<CompteAdmin>(`/admin/utilisateurs/${id}/suspendre`, {
        motif,
      }),
    );
  }

  async reactiver(id: number): Promise<CompteAdmin> {
    return firstValueFrom(
      this.api.post<CompteAdmin>(`/admin/utilisateurs/${id}/reactiver`, {}),
    );
  }

  /**
   * Supprime définitivement un compte.
   *
   * Le serveur refuse (409) de supprimer le dernier administrateur, le
   * compte de l'appelant, ou un compte ayant déposé ou validé un texte
   * du corpus — son nom figure dans la table de provenance publiée.
   */
  async supprimer(id: number): Promise<void> {
    await firstValueFrom(this.api.delete<void>(`/admin/utilisateurs/${id}`));
  }

  message(erreur: unknown): string {
    if (erreur instanceof ErreurApi) return erreur.message;
    return "L'opération a échoué.";
  }
}

export interface ForfaitAdmin {
  code: string;
  libelle: string;
  prix_fcfa: number;
  credits: number;
  argumentaire: string;
  atouts: string[];
  essai: boolean;
  actif: boolean;
  ordre: number;
  cout_variable_fcfa: number;
  /** `null` sur le gratuit : c'est un coût d'acquisition, pas une vente. */
  marge: number | null;
  abonnes: number;
}

export interface ForfaitEcriture {
  libelle: string;
  prix_fcfa: number;
  credits: number;
  argumentaire: string;
  atouts: string[];
  essai: boolean;
  actif: boolean;
  ordre: number;
}

export interface Signalement {
  id: number;
  message_id: number;
  motif: string;
  commentaire: string | null;
  statut: 'ouvert' | 'traite' | 'ecarte';
  correction: string | null;
  cree_le: string;
  traite_le: string | null;
  email: string | null;
  question: string | null;
  reponse: string | null;
}
