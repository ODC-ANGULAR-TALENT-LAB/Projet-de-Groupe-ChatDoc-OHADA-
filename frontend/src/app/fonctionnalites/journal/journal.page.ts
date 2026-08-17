import { Component, inject, signal } from '@angular/core';
import { SlicePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { EntreeJournal } from '../../core/models';
import { CorpusService } from '../../core/services/corpus.service';

/**
 * Journal des mises à jour du corpus.
 *
 * POURQUOI CETTE PAGE EXISTE. Un corpus qui change sans le dire vaut à
 * peine mieux qu'un corpus périmé : l'utilisateur professionnel doit
 * pouvoir constater qu'on l'entretient, et savoir ce qui a bougé depuis
 * sa dernière recherche. Le cahier des charges (§2 ter) en fait un
 * élément de la transparence affichée.
 *
 * Rien n'est saisi à la main ici : chaque entrée est produite par la
 * validation d'un dépôt, et les résumés viennent du diff relu par le
 * juriste au moment où il a engagé sa signature.
 */
@Component({
  selector: 'app-journal',
  standalone: true,
  imports: [RouterLink, SlicePipe],
  template: `
    <section class="page">
      <header>
        <h1>Journal des mises à jour</h1>
        <p class="intro">
          Ce qui a changé dans le corpus, du plus récent au plus ancien.
        </p>
      </header>

      @if (entrees() === null) {
        <p class="vide">Chargement…</p>
      } @else if (!entrees()!.length) {
        <p class="vide">
          Aucune publication enregistrée pour l'instant. Les textes chargés
          avant la mise en place du journal figurent dans la
          <a routerLink="/methodologie">table de provenance</a>.
        </p>
      } @else {
        <ol class="fil">
          @for (entree of entrees(); track entree.depot_id) {
            <li>
              <div class="date">
                {{ entree.publie_le ? (entree.publie_le | slice: 0 : 10) : '—' }}
              </div>

              <article>
                <h2>
                  <span class="sigle">{{ entree.sigle }}</span>
                  {{ entree.version }}
                </h2>
                <p class="titre">{{ entree.titre }}</p>

                <div class="compteurs">
                  <span class="pastille total">{{ entree.nb_articles }} articles</span>
                  @if (entree.ajoutes) {
                    <span class="pastille ajoute">{{ entree.ajoutes }} ajouté(s)</span>
                  }
                  @if (entree.modifies) {
                    <span class="pastille modifie">{{ entree.modifies }} modifié(s)</span>
                  }
                  @if (entree.abroges) {
                    <span class="pastille abroge">{{ entree.abroges }} abrogé(s)</span>
                  }
                </div>

                @if (entree.faits_marquants.length) {
                  <ul class="faits">
                    @for (fait of entree.faits_marquants; track fait.numero) {
                      <li>
                        <strong>Article {{ fait.numero }}</strong> — {{ fait.resume }}
                      </li>
                    }
                  </ul>
                }
              </article>
            </li>
          }
        </ol>
      }
    </section>
  `,
  styleUrl: './journal.page.scss',
})
export class JournalPage {
  private readonly corpus = inject(CorpusService);

  protected readonly entrees = signal<EntreeJournal[] | null>(null);

  constructor() {
    void this.charger();
  }

  private async charger(): Promise<void> {
    try {
      this.entrees.set(await this.corpus.journal());
    } catch {
      this.entrees.set([]);
    }
  }
}
