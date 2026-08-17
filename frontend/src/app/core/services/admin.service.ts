import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { HttpClient } from '@angular/common/http';
import { environnement } from '../../../environnements/environnement';
import { ApiService } from './api.service';

export interface Probleme {
  niveau: 'bloquant' | 'avertissement';
  message: string;
}

export interface ArticleDepot {
  numero: string;
  chemin: string;
  contenu: string;
  page_debut?: number | null;
}

export interface Depot {
  id: number;
  nom_fichier: string;
  sha256: string;
  source_url: string;
  sigle: string;
  titre: string;
  type: string;
  version: string;
  date_consolidation: string;
  statut: 'en_attente' | 'valide' | 'rejete';
  nb_pages: number | null;
  nb_articles: number;
  nb_bloquants: number;
  cree_le: string;
  texte_id?: number | null;
}

/** Statut d'un article du dépôt face au corpus en vigueur. */
export type StatutDiff = 'ajoute' | 'modifie' | 'abroge' | 'inchange';

/**
 * Un article situé par rapport au corpus en vigueur.
 *
 * `statut` vient d'une comparaison textuelle déterministe côté serveur.
 * `resume` et `portee` viennent du modèle et ne sont qu'un confort de
 * lecture : le modèle ne décide jamais du statut.
 */
export interface EntreeDiff {
  numero: string;
  statut: StatutDiff;
  article_id?: number | null;
  ancien?: string | null;
  nouveau?: string | null;
  chemin: string;
  similarite: number;
  resume?: string | null;
  portee?: 'majeure' | 'mineure' | null;
}

export interface DepotDetail extends Depot {
  articles: ArticleDepot[];
  problemes: Probleme[];
  analyse: EntreeDiff[];
  articles_retenus: string[];
}

export interface EtatTexte {
  id: number;
  sigle: string;
  version: string;
  date_consolidation: string;
  valide_par: string | null;
  articles: number;
  vectorises: number;
  pret: boolean;
}

/** Provenance saisie au dépôt. Tous les champs sont obligatoires. */
export interface Provenance {
  source_url: string;
  sigle: string;
  titre: string;
  version: string;
  date_consolidation: string;
  type: string;
  page_debut: number;
}

/**
 * Back-office d'ingestion.
 *
 * Téléverser alimente le CORPUS interrogé, jamais les poids du modèle :
 * il n'y a aucun entraînement ici. Et rien n'entre dans le corpus sans
 * une validation humaine explicite.
 */
@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);

  readonly depots = signal<Depot[] | null>(null);
  readonly corpus = signal<EtatTexte[] | null>(null);

  async chargerDepots(): Promise<void> {
    this.depots.set(await firstValueFrom(this.api.get<Depot[]>('/admin/depots')));
  }

  async chargerCorpus(): Promise<void> {
    this.corpus.set(
      await firstValueFrom(this.api.get<EtatTexte[]>('/admin/corpus/etat')),
    );
  }

  async detail(id: number): Promise<DepotDetail> {
    return firstValueFrom(this.api.get<DepotDetail>(`/admin/depots/${id}`));
  }

  /**
   * Téléverse un PDF. Ne l'ajoute PAS au corpus.
   *
   * Passe par HttpClient directement : un envoi multipart ne doit pas
   * porter d'en-tête Content-Type fixé à la main, le navigateur ajoute
   * lui-même la frontière.
   */
  async deposer(fichier: File, provenance: Provenance): Promise<DepotDetail> {
    const corps = new FormData();
    corps.append('fichier', fichier);
    for (const [cle, valeur] of Object.entries(provenance)) {
      corps.append(cle, String(valeur));
    }
    return firstValueFrom(
      this.http.post<DepotDetail>(`${environnement.urlApi}/admin/depots`, corps),
    );
  }

  /**
   * Situe le dépôt par rapport au corpus déjà en vigueur.
   *
   * C'est l'étape qui rend une mise à jour tenable : sans elle, le
   * juriste reçoit quatre cents articles sans savoir lesquels ont bougé.
   */
  async analyser(id: number): Promise<DepotDetail> {
    return firstValueFrom(
      this.api.post<DepotDetail>(`/admin/depots/${id}/analyser`, {}),
    );
  }

  /** Enregistre les articles que le juriste déclare avoir relus. */
  async marquerRelu(id: number, numeros: string[]): Promise<DepotDetail> {
    return firstValueFrom(
      this.api.post<DepotDetail>(`/admin/depots/${id}/relu`, { numeros }),
    );
  }

  /** Calcule les embeddings manquants du texte, en tâche de fond. */
  async vectoriser(texteId: number): Promise<{ message: string }> {
    return firstValueFrom(
      this.api.post<{ message: string }>(`/admin/textes/${texteId}/vectoriser`, {}),
    );
  }

  async valider(id: number): Promise<void> {
    await firstValueFrom(this.api.post<Depot>(`/admin/depots/${id}/valider`, {}));
    await this.chargerDepots();
    await this.chargerCorpus();
  }

  async rejeter(id: number): Promise<void> {
    await firstValueFrom(this.api.post<Depot>(`/admin/depots/${id}/rejeter`, {}));
    await this.chargerDepots();
  }
}
