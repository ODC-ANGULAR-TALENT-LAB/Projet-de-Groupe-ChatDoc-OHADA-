import { Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Message } from '../../../core/models';
import { AvertissementDeontoComponent } from '../../../partage/composants/avertissement-deonto.component';
import { BlocBaseLegaleComponent } from './bloc-base-legale.component';
import { IconeComponent } from '../../../partage/composants/icone.component';
import { MarkdownComponent } from '../../../partage/composants/markdown.component';
import { ChatService } from '../../../core/services/chat.service';

/**
 * Un tour de conversation.
 *
 * Ordre d'affichage imposé (F.5) : la RÉPONSE d'abord, les citations
 * ensuite. Jamais l'inverse — les citations n'existent qu'après
 * validation serveur, et afficher une référence avant de savoir si elle
 * survivra au contrôle reviendrait à montrer une preuve qu'on pourrait
 * ensuite retirer.
 */
@Component({
  selector: 'app-bulle-message',
  standalone: true,
  imports: [
    BlocBaseLegaleComponent,
    AvertissementDeontoComponent,
    IconeComponent,
    MarkdownComponent,
    FormsModule,
  ],
  template: `
    @if (message().role === 'user') {
      <div class="tour question">
        <p class="texte">{{ message().contenu }}</p>
      </div>
    } @else {
      <div class="tour reponse" [class.refus]="message().refus"
           [class.sans-synthese]="message().sansSynthese">
        @if (message().sansSynthese) {
          <p class="etiquette">Recherche documentaire — sans rédaction</p>
        }
        <app-markdown class="texte" [texte]="message().contenu" />

        @if (message().citations?.length) {
          <app-bloc-base-legale [citations]="message().citations!" />
        }

        @if (message().miseEnGarde) {
          <p class="mise-en-garde">{{ message().miseEnGarde }}</p>
        }

        <app-avertissement-deonto />

        <!-- La réponse est faite pour être reprise dans une note de
             travail : le cahier des charges en fait un besoin explicite
             de l'expert-comptable (§6). -->
        <div class="actions">
          <button type="button" class="action" (click)="copier()">
            <app-icone [nom]="copie() ? 'valide' : 'copier'" />
            {{ copie() ? 'Copié' : 'Copier' }}
          </button>

          @if (message().messageId) {
            <button type="button" class="action" (click)="exporter()">
              <app-icone nom="telecharger" />
              Exporter en PDF
            </button>

            <!-- Signaler n'est pas un aveu de faiblesse : c'est la
                 procédure qualité du cahier des charges (§16 ter).
                 Assumer une erreur et la corriger protège davantage
                 qu'un silence. -->
            <button type="button" class="action" (click)="ouvrirSignalement()">
              <app-icone nom="signaler" />
              {{ signale() ? 'Signalé' : 'Signaler' }}
            </button>
          }
        </div>

        @if (signalementOuvert()) {
          <form class="signalement" (ngSubmit)="envoyerSignalement()">
            <label for="motif-{{ message().messageId }}">
              Qu'est-ce qui ne va pas dans cette réponse ?
            </label>
            <select
              id="motif-{{ message().messageId }}"
              name="motif"
              [(ngModel)]="motif"
            >
              <option value="article_faux">L'article cité ne dit pas cela</option>
              <option value="article_perime">L'article cité est périmé</option>
              <option value="hors_sujet">La réponse est hors sujet</option>
              <option value="reponse_incomplete">La réponse est incomplète</option>
              <option value="autre">Autre</option>
            </select>

            <label for="detail-{{ message().messageId }}">
              Précisez (facultatif)
            </label>
            <textarea
              id="detail-{{ message().messageId }}"
              name="commentaire"
              rows="2"
              [(ngModel)]="commentaire"
            ></textarea>

            <div class="boutons">
              <button type="submit" class="principal">Envoyer le signalement</button>
              <button type="button" class="secondaire"
                      (click)="signalementOuvert.set(false)">
                Annuler
              </button>
            </div>
          </form>
        }
      </div>
    }
  `,
  styles: `
    .tour {
      margin-bottom: var(--e6);
    }

    /* La question est à droite, en aplat bleu nuit ; l'angle inférieur
       droit reste vif pour désigner le locuteur. */
    .question {
      background: var(--bleu-nuit);
      color: #fff;
      padding: 0.85rem 1.1rem;
      border-radius: var(--rayon-carte) var(--rayon-carte) 2px var(--rayon-carte);
      margin-left: auto;
      max-width: 85%;
      width: fit-content;
      line-height: 1.6;
    }

    /* La réponse est une carte blanche posée sur le papier : la
       profondeur vient du contraste de tons et d'un filet, jamais d'une
       ombre portée. */
    .reponse {
      background: var(--surface);
      border: 1px solid var(--bordure);
      border-radius: var(--rayon-carte);
      padding: var(--e6);
    }

    /* Un refus a son propre rendu : sobre et NON alarmant. C'est une
       fonctionnalité revendiquée, pas une erreur — ni rouge, ni icône
       d'avertissement. */
    .refus {
      background: var(--fond-refus);
      border-style: dashed;
    }

    /* Mode dégradé : les articles sont là, la rédaction manque. On le
       dit franchement plutôt que de laisser croire à une réponse. */
    .sans-synthese {
      border-left: 3px solid var(--or);
    }

    .etiquette {
      margin: 0 0 0.5rem;
      font-size: var(--t-xs);
      font-weight: 600;
      letter-spacing: 0.07em;
      text-transform: uppercase;
      color: var(--or-fonce);
    }

    .texte {
      display: block;
      margin: 0;
    }

    .actions {
      display: flex;
      gap: var(--e2);
      margin-top: var(--e3);
      padding-top: var(--e2);
      border-top: 1px solid var(--bordure);
    }

    .action {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      /* Action secondaire, à l'intérieur d'une carte : 36 px suffisent,
         la règle des 44 px vaut pour les cibles isolées. */
      min-height: 36px;
      padding: 0.35rem 0.6rem;
      background: none;
      border: 1px solid transparent;
      border-radius: var(--rayon);
      color: var(--gris-texte);
      font: inherit;
      font-size: var(--t-xs);
      cursor: pointer;

      --taille-icone: 0.95rem;

      &:hover,
      &:focus-visible {
        border-color: var(--bordure);
        color: var(--bleu-nuit);
      }
    }

    /* Le formulaire de signalement : sobre et non alarmant. Signaler
       est une procedure qualite, pas une denonciation. */
    .signalement {
      margin-top: var(--e3);
      padding: var(--e3);
      background: var(--surface-basse);
      border-radius: var(--rayon-carte);
      font-size: var(--t-md);

      label {
        display: block;
        margin-bottom: var(--e1);
        font-weight: 500;
        color: var(--gris-texte);
      }

      select,
      textarea {
        width: 100%;
        margin-bottom: var(--e3);
        padding: 0.45rem 0.55rem;
        font: inherit;
        font-size: var(--t-md);
        background: var(--surface);
        border: 1px solid var(--gris-bordure);
        border-radius: var(--rayon);
        resize: vertical;
      }

      .boutons {
        display: flex;
        gap: var(--e2);
        flex-wrap: wrap;
      }
    }

    .mise-en-garde {
      margin: 0.75rem 0 0.5rem;
      padding-left: 0.7rem;
      border-left: 2px solid var(--gris-bordure);
      font-size: var(--t-md);
      color: var(--gris-texte);
    }
  `,
})
export class BulleMessageComponent {
  private readonly chat = inject(ChatService);

  readonly message = input.required<Message>();

  /** Repasse a faux au bout de deux secondes : un retour, pas un etat. */
  protected readonly copie = signal(false);
  protected readonly signalementOuvert = signal(false);
  protected readonly signale = signal(false);

  protected motif = 'article_faux';
  protected commentaire = '';

  protected async copier(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.message().contenu);
      this.copie.set(true);
      setTimeout(() => this.copie.set(false), 2000);
    } catch {
      // Presse-papiers refuse (contexte non securise, permission) :
      // on n'affiche pas d'erreur pour une action de confort.
    }
  }

  protected async exporter(): Promise<void> {
    const identifiant = this.message().messageId;
    if (identifiant) await this.chat.exporter(identifiant);
  }

  protected ouvrirSignalement(): void {
    this.signalementOuvert.update((ouvert) => !ouvert);
  }

  protected async envoyerSignalement(): Promise<void> {
    const identifiant = this.message().messageId;
    if (!identifiant) return;

    await this.chat.signaler(identifiant, this.motif, this.commentaire);
    this.signalementOuvert.set(false);
    this.signale.set(true);
    this.commentaire = '';
  }
}
