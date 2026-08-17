import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environnement } from '../../../environnements/environnement';
import { ApiService, ErreurApi } from './api.service';

export interface ModeleConformite {
  cle: string;
  libelle: string;
  sigle: string;
  numero: string;
}

export interface PointConformite {
  repere: string;
  libelle: string;
  statut: 'conforme' | 'ecart' | 'a_verifier';
  constat: string;
}

/**
 * Le rapport rendu par le serveur.
 *
 * Aucun indice global n'y figure, et c'est délibéré : un pourcentage
 * laisserait croire à une garantie de conformité que le produit refuse
 * explicitement de donner.
 */
export interface RapportConformite {
  modele: string;
  article_id: number;
  sigle: string;
  numero: string;
  version_corpus: string;
  points: PointConformite[];
  compte: Record<string, number>;
}

@Injectable({ providedIn: 'root' })
export class ConformiteService {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);

  async modeles(): Promise<ModeleConformite[]> {
    return firstValueFrom(
      this.api.get<ModeleConformite[]>('/conformite/modeles'),
    );
  }

  /**
   * Envoie le document. Il n'est jamais conservé côté serveur.
   *
   * Passe par HttpClient directement : un envoi multipart ne doit pas
   * porter d'en-tête Content-Type fixé à la main, le navigateur ajoute
   * lui-même la frontière.
   */
  async analyser(fichier: File, modele: string): Promise<RapportConformite> {
    const corps = new FormData();
    corps.append('fichier', fichier);
    corps.append('modele', modele);
    return firstValueFrom(
      this.http.post<RapportConformite>(
        `${environnement.urlApi}/conformite/analyser`,
        corps,
      ),
    );
  }

  /** Remonte le message du serveur : il explique précisément le refus. */
  message(erreur: unknown): string {
    if (erreur instanceof ErreurApi) return erreur.message;
    const detail = (erreur as { error?: { detail?: unknown } })?.error?.detail;
    if (typeof detail === 'string') return detail;
    return "L'analyse a échoué.";
  }
}
