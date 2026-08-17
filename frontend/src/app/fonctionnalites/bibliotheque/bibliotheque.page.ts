import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  NoeudSommaire,
  ResultatRecherche,
  Texte,
} from '../../core/models';
import { CorpusService } from '../../core/services/corpus.service';
import { SommaireArbreComponent } from './composants/sommaire-arbre.component';

/**
 * La bibliothèque : le corpus, rangé et lisible.
 *
 * Tout est public et hors quota — consulter un texte ne coûte rien et
 * n'appelle aucun modèle. La version et la date de consolidation sont
 * affichées sur chaque texte : c'est une condition de confiance
 * professionnelle, pas un détail.
 */
@Component({
  selector: 'app-bibliotheque',
  standalone: true,
  imports: [FormsModule, RouterLink, SommaireArbreComponent],
  template: `
    <section class="page">
      <header>
        <h1>Bibliothèque</h1>
        <p class="intro">
          Les textes officiels du corpus, consultables librement.
        </p>
      </header>

      <form class="recherche" (ngSubmit)="lancerRecherche()" role="search">
        <label class="invisible" for="q">Rechercher dans le corpus</label>
        <input
          id="q"
          name="q"
          type="search"
          placeholder="Rechercher un terme dans le corpus…"
          [(ngModel)]="termeModele"
        />
        <button type="submit" class="secondaire" [disabled]="chargeRecherche()">
          Rechercher
        </button>
      </form>

      @if (resultats(); as trouves) {
        <section class="resultats" aria-label="Résultats de recherche">
          <div class="entete-resultats">
            <h2>
              {{ trouves.length }} résultat{{ trouves.length > 1 ? 's' : '' }}
            </h2>
            <button type="button" class="lien" (click)="effacerRecherche()">
              Effacer
            </button>
          </div>
          @for (resultat of trouves; track resultat.id) {
            <a class="resultat" [routerLink]="['/article', resultat.id]">
              <span class="reference">
                {{ resultat.sigle }} — Article {{ resultat.numero }}
              </span>
              <span class="chemin">{{ resultat.chemin }}</span>
              <span class="extrait">{{ resultat.extrait }}…</span>
            </a>
          } @empty {
            <p class="vide">
              Aucun article ne contient ces termes. La recherche porte sur les
              mots exacts du texte, pas sur leur sens — le chat, lui, comprend
              les questions formulées librement.
            </p>
          }
        </section>
      }

      @if (erreur()) {
        <p class="erreur" role="alert">{{ erreur() }}</p>
      } @else if (textes() === null) {
        <p class="attente" role="status">Chargement du corpus…</p>
      } @else if (!textes()!.length) {
        <p class="vide">
          Aucun texte n'est encore chargé dans le corpus.
        </p>
      } @else {
        @for (texte of textes(); track texte.id) {
          <article class="texte">
            <button
              type="button"
              class="entete-texte"
              [attr.aria-expanded]="texteOuvert() === texte.id"
              (click)="ouvrir(texte)"
            >
              <span class="sigle">{{ texte.sigle }}</span>
              <span class="titre">{{ texte.titre }}</span>
            </button>

            <dl class="meta">
              <div>
                <dt>Version</dt>
                <dd>{{ texte.version }}</dd>
              </div>
              <div>
                <dt>Consolidé au</dt>
                <dd>{{ texte.date_consolidation }}</dd>
              </div>
            </dl>

            @if (texteOuvert() === texte.id) {
              @if (sommaire(); as noeuds) {
                <app-sommaire-arbre [sommaire]="noeuds" />
              } @else {
                <p class="attente" role="status">Chargement du sommaire…</p>
              }
            }
          </article>
        }
      }
    </section>
  `,
  styleUrl: './bibliotheque.page.scss',
})
export class BibliothequePage {
  private readonly corpus = inject(CorpusService);

  protected readonly textes = this.corpus.textes;
  protected readonly sommaire = signal<NoeudSommaire[] | null>(null);
  protected readonly texteOuvert = signal<number | null>(null);
  protected readonly resultats = signal<ResultatRecherche[] | null>(null);
  protected readonly chargeRecherche = signal(false);
  protected readonly erreur = signal<string | null>(null);

  private terme = '';

  protected get termeModele(): string {
    return this.terme;
  }
  protected set termeModele(valeur: string) {
    this.terme = valeur;
  }

  constructor() {
    void this.charger();
  }

  protected async ouvrir(texte: Texte): Promise<void> {
    if (this.texteOuvert() === texte.id) {
      this.texteOuvert.set(null);
      return;
    }
    this.texteOuvert.set(texte.id);
    this.sommaire.set(null);
    this.sommaire.set(await this.corpus.sommaire(texte.id));
  }

  protected async lancerRecherche(): Promise<void> {
    const terme = this.terme.trim();
    if (terme.length < 2) return;

    this.chargeRecherche.set(true);
    try {
      this.resultats.set(await this.corpus.rechercher(terme));
    } catch {
      this.erreur.set('La recherche a échoué.');
    } finally {
      this.chargeRecherche.set(false);
    }
  }

  protected effacerRecherche(): void {
    this.resultats.set(null);
    this.terme = '';
  }

  private async charger(): Promise<void> {
    try {
      await this.corpus.chargerTextes();
    } catch {
      this.erreur.set("Le corpus n'a pas pu être chargé.");
    }
  }
}
