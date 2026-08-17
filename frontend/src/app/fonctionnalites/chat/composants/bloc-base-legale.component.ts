import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Citation } from '../../../core/models';
import { IconeComponent } from '../../../partage/composants/icone.component';

/**
 * Le bloc « Base légale » — l'élément le plus important de l'interface.
 *
 * C'est la signature visuelle du produit : il n'existe qu'une seule fois
 * dans le code et il est réutilisé partout. Carte blanche posée sur la
 * réponse, filet doré de 4 px à gauche, référence en tête, extrait en
 * dessous, référence entière cliquable.
 *
 * Les citations reçues sont déjà validées par le serveur : chaque
 * article_id existait bien dans le contexte fourni au modèle. Ce
 * composant n'a donc rien à revérifier — il affiche une preuve.
 *
 * L'EXTRAIT EST EN SÉRIF, LE COMMENTAIRE EN SANS. C'est la règle
 * typographique de tout le produit : l'empattement est la voix de la
 * loi, le linéal celle de l'interface. Un lecteur doit pouvoir dire d'un
 * coup d'œil ce qui est le texte officiel et ce qui ne l'est pas.
 *
 * Écart par rapport au guide : syntaxe de contrôle @for / @if
 * d'Angular 17+, plutôt que *ngFor / *ngIf. Même rendu, mais c'est
 * l'idiome de la version imposée par la stack.
 */
@Component({
  selector: 'app-bloc-base-legale',
  standalone: true,
  imports: [RouterLink, IconeComponent],
  template: `
    @if (citations().length) {
      <section class="base-legale" aria-label="Base légale">
        @for (citation of citations(); track citation.article_id) {
          <article class="bloc">
            <p class="intitule">
              <app-icone nom="balance" />
              Base légale
            </p>

            <h3 class="reference">
              Article {{ citation.numero }} de l'{{ citation.sigle }}
            </h3>

            @if (citation.chemin) {
              <p class="chemin">{{ citation.chemin }}</p>
            }

            <blockquote class="extrait">{{ citation.extrait }}</blockquote>

            @if (citation.pourquoi) {
              <p class="pourquoi">{{ citation.pourquoi }}</p>
            }

            <a class="ouvrir" [routerLink]="['/article', citation.article_id]">
              Voir l'article complet
              <app-icone nom="fleche" />
            </a>
          </article>
        }
      </section>
    }
  `,
  styles: `
    .base-legale {
      display: flex;
      flex-direction: column;
      /* Espace généreux entre deux citations : le lecteur doit traiter
         chaque fondement séparément, pas les lire comme une liste. */
      gap: var(--e4);
      margin: var(--e4) 0;
    }

    .bloc {
      background: var(--surface);
      border: 1px solid var(--bordure);
      /* Le filet doré est l'accent le plus fort de l'interface. Il est
         réservé à ce bloc : c'est ce qui le rend reconnaissable. */
      border-left: 4px solid var(--or);
      border-radius: 0 var(--rayon-carte) var(--rayon-carte) 0;
      padding: var(--e4) var(--e4) var(--e3);
    }

    .intitule {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      margin: 0 0 var(--e2);
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      color: var(--or-fonce);

      --taille-icone: 1rem;
    }

    .reference {
      margin: 0;
      font-family: var(--police-serif);
      font-size: 1.3rem;
      font-weight: 600;
      line-height: 1.3;
      color: var(--bleu-nuit);
    }

    .chemin {
      margin: var(--e1) 0 0;
      font-size: 0.75rem;
      color: var(--gris-texte);
    }

    .extrait {
      margin: var(--e3) 0 0;
      padding-left: var(--e3);
      border-left: 2px solid var(--gris-bordure);
      font-family: var(--police-serif);
      font-size: 1.05rem;
      font-style: italic;
      line-height: 1.6;
      color: var(--texte);
    }

    .pourquoi {
      margin: var(--e3) 0 0;
      font-size: 0.82rem;
      color: var(--gris-texte);
    }

    .ouvrir {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      margin-top: var(--e3);
      /* Cible tactile : le lien dépasse le texte de 8 px en haut et en
         bas pour atteindre les 44 px réglementaires. */
      padding: 0.5rem 0;
      color: var(--or-fonce);
      font-size: 0.9rem;
      font-weight: 600;
      text-decoration: none;

      --taille-icone: 1rem;

      &:hover,
      &:focus-visible {
        text-decoration: underline;
      }

      /* Le déplacement de la flèche dit « on part vers ailleurs ». Il
         est purement indicatif et disparaît en mouvement réduit. */
      app-icone {
        transition: transform 160ms ease-out;
      }

      &:hover app-icone {
        transform: translateX(3px);
      }
    }
  `,
})
export class BlocBaseLegaleComponent {
  readonly citations = input.required<Citation[]>();
}
