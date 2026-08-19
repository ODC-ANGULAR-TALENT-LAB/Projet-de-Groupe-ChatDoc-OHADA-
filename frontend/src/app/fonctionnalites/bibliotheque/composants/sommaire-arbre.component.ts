import {
  ChangeDetectionStrategy,
  Component,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { NoeudSommaire } from '../../../core/models';

/**
 * Sommaire arborescent d'un texte.
 *
 * L'arbre est reconstruit à partir du champ `chemin` des articles, tel
 * que le découpage l'a établi — c'est le même chemin qui préfixe la
 * vectorisation et qui s'affiche dans le fil d'Ariane. Une seule source
 * de vérité pour la hiérarchie du corpus.
 */
@Component({
  selector: 'app-sommaire-arbre',
  standalone: true,
  imports: [RouterLink],
  // Le sommaire de l'AUSCGIE compte 204 sections. Sans OnPush, chacune
  // est réévaluée à chaque cycle de détection déclenché n'importe où
  // dans l'application — y compris par une frappe dans la recherche.
  // L'état de l'arbre tient dans un signal : OnPush est donc sûr ici,
  // le composant se redessine quand ce signal change et pas autrement.
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ul class="arbre">
      @for (noeud of sommaire(); track noeud.chemin) {
        <li class="section">
          <button
            type="button"
            class="entete"
            [attr.aria-expanded]="estOuvert(noeud.chemin)"
            (click)="basculer(noeud.chemin)"
          >
            <span class="chevron" [class.ouvert]="estOuvert(noeud.chemin)"
                  aria-hidden="true">›</span>
            <span class="chemin">{{ noeud.chemin || 'Sans niveau' }}</span>
            <span class="compte">{{ noeud.articles.length }}</span>
          </button>

          @if (estOuvert(noeud.chemin)) {
            <ul class="articles">
              @for (article of noeud.articles; track article.id) {
                <li>
                  <a [routerLink]="['/article', article.id]">
                    Article {{ article.numero }}
                  </a>
                </li>
              }
            </ul>
          }
        </li>
      }
    </ul>
  `,
  styles: `
    .arbre,
    .articles {
      list-style: none;
      margin: 0;
      padding: 0;
    }

    .section {
      border-bottom: 1px solid var(--bordure);
    }

    .entete {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      width: 100%;
      background: none;
      border: none;
      padding: 0.7rem 0.25rem;
      font: inherit;
      font-size: 0.9rem;
      text-align: left;
      color: var(--texte);
      cursor: pointer;
    }

    .chevron {
      color: var(--or);
      transition: transform 0.15s ease;
      flex-shrink: 0;
    }

    .chevron.ouvert {
      transform: rotate(90deg);
    }

    @media (prefers-reduced-motion: reduce) {
      .chevron {
        transition: none;
      }
    }

    .chemin {
      flex: 1;
      font-family: var(--police-serif);
    }

    .compte {
      font-size: 0.7rem;
      color: var(--gris-texte);
      background: var(--fond);
      border-radius: 999px;
      padding: 0.05rem 0.45rem;
      flex-shrink: 0;
    }

    .articles {
      padding: 0 0 0.6rem 1.6rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;

      a {
        display: inline-block;
        font-size: 0.8rem;
        color: var(--bleu-nuit);
        text-decoration: none;
        border: 1px solid var(--bordure);
        border-radius: 4px;
        padding: 0.2rem 0.5rem;

        &:hover,
        &:focus-visible {
          border-color: var(--or);
        }
      }
    }
  `,
})
export class SommaireArbreComponent {
  readonly sommaire = input.required<NoeudSommaire[]>();

  private readonly ouverts = signal(new Set<string>());

  protected estOuvert(chemin: string): boolean {
    return this.ouverts().has(chemin);
  }

  protected basculer(chemin: string): void {
    this.ouverts.update((actuels) => {
      const suivants = new Set(actuels);
      if (!suivants.delete(chemin)) suivants.add(chemin);
      return suivants;
    });
  }
}
