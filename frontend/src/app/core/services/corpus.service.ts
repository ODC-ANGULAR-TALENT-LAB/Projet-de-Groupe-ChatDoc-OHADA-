import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { Article, EntreeJournal, LigneProvenance, NoeudSommaire, ResultatRecherche, Texte } from '../models';
import { ApiService } from './api.service';

/**
 * Textes, sommaires et articles, avec cache.
 *
 * Le corpus ne change pas pendant une session : un sommaire ou un
 * article déjà lu n'est jamais redemandé. C'est ce qui rend la lecture
 * instantanée et permet à la bibliothèque de rester consultable
 * hors ligne, là où le chat exige la connexion.
 */
@Injectable({ providedIn: 'root' })
export class CorpusService {
  private readonly api = inject(ApiService);
  private readonly cacheArticles = new Map<number, Article>();
  private readonly cacheSommaires = new Map<number, NoeudSommaire[]>();

  readonly textes = signal<Texte[] | null>(null);

  async chargerTextes(): Promise<Texte[]> {
    const dejaLus = this.textes();
    if (dejaLus) return dejaLus;

    const textes = await firstValueFrom(this.api.get<Texte[]>('/textes'));
    this.textes.set(textes);
    return textes;
  }

  async sommaire(texteId: number): Promise<NoeudSommaire[]> {
    const enCache = this.cacheSommaires.get(texteId);
    if (enCache) return enCache;

    const sommaire = await firstValueFrom(
      this.api.get<NoeudSommaire[]>(`/textes/${texteId}/sommaire`),
    );
    this.cacheSommaires.set(texteId, sommaire);
    return sommaire;
  }

  async article(id: number): Promise<Article> {
    const enCache = this.cacheArticles.get(id);
    if (enCache) return enCache;

    const article = await firstValueFrom(this.api.get<Article>(`/articles/${id}`));
    this.cacheArticles.set(id, article);
    return article;
  }

  /** Recherche plein texte : gratuite, hors quota, sans appel au modèle. */
  async rechercher(q: string): Promise<ResultatRecherche[]> {
    return firstValueFrom(this.api.get<ResultatRecherche[]>('/recherche', { q }));
  }

  /**
   * La table de provenance publiée.
   *
   * Elle n'est pas décorative : c'est elle qui permet de remonter toute
   * réponse contestée à sa source exacte, et donc la protection du
   * projet (§2 ter du cahier des charges).
   */
  async provenance(): Promise<LigneProvenance[]> {
    return firstValueFrom(this.api.get<LigneProvenance[]>('/provenance'));
  }

  /** Ce qui a changé dans le corpus, du plus récent au plus ancien. */
  async journal(): Promise<EntreeJournal[]> {
    return firstValueFrom(this.api.get<EntreeJournal[]>('/journal'));
  }
}
