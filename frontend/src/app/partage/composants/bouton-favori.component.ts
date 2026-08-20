import { Component, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../core/services/auth.service';
import { FavorisService } from '../../core/services/favoris.service';
import { IconeComponent } from './icone.component';

/**
 * Mettre un article de côté, et noter pourquoi.
 *
 * DEUX GESTES, UN SEUL BOUTON. Marquer et annoter sont la même
 * intention — « cet article compte pour moi » — et les séparer
 * obligerait l'utilisateur à choisir avant de savoir ce qu'il veut
 * écrire. Le champ d'annotation n'apparaît qu'une fois l'article
 * marqué : proposer d'annoter ce qu'on ne suit pas n'a pas de sens.
 *
 * L'ANNOTATION EST PRIVÉE. Rien ne l'expose à un autre utilisateur, ni
 * au juriste qui tient le corpus : ce sont des notes de travail sur des
 * dossiers clients.
 */
@Component({
  selector: 'app-bouton-favori',
  standalone: true,
  imports: [FormsModule, IconeComponent],
  template: `
    @if (auth.connecte()) {
      <div class="bloc">
        <button
          type="button"
          class="bascule"
          [class.actif]="marque()"
          [disabled]="occupe()"
          [attr.aria-pressed]="marque()"
          (click)="basculer()"
        >
          <app-icone nom="favori" />
          {{ marque() ? 'En favori' : 'Mettre en favori' }}
        </button>

        @if (marque()) {
          <div class="annotation">
            <label [attr.for]="'note-' + articleId()">
              Note personnelle (visible de vous seul)
            </label>
            <textarea
              [id]="'note-' + articleId()"
              rows="3"
              placeholder="Pourquoi cet article compte pour vous, le dossier concerné…"
              [ngModel]="note()"
              (ngModelChange)="note.set($event)"
            ></textarea>

            <div class="pied">
              @if (enregistre()) {
                <span class="confirme" role="status">
                  <app-icone nom="valide" />
                  Enregistrée
                </span>
              }
              <button
                type="button"
                class="enregistrer"
                [disabled]="occupe()"
                (click)="enregistrerNote()"
              >
                Enregistrer la note
              </button>
            </div>
          </div>
        }

        @if (erreur()) {
          <p class="erreur" role="alert">{{ erreur() }}</p>
        }
      </div>
    }
  `,
  styles: `
    .bloc {
      margin: 1.5rem 0;
    }

    .bascule {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      min-height: 44px;
      padding: 0.5rem 0.9rem;
      font: inherit;
      font-size: var(--t-md);
      font-weight: 500;
      color: var(--bleu-nuit);
      background: var(--surface);
      border: 1px solid var(--gris-bordure);
      border-radius: var(--rayon);
      cursor: pointer;

      &:hover:not(:disabled) {
        border-color: var(--or);
      }

      /* L'état marqué se lit à la couleur ET au remplissage de
         l'icône : la couleur seule ne suffit pas à porter une
         information. */
      &.actif {
        color: var(--or-fonce);
        background: var(--or-pale);
        border-color: var(--or);

        app-icone {
          fill: currentColor;
        }
      }

      &:disabled {
        opacity: 0.55;
        cursor: not-allowed;
      }
    }

    .annotation {
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
      margin-top: 0.75rem;

      label {
        font-size: var(--t-xs);
        color: var(--gris-texte);
      }

      textarea {
        padding: 0.6rem;
        font: inherit;
        font-size: var(--t-md);
        line-height: 1.6;
        background: var(--surface);
        border: 1px solid var(--gris-bordure);
        border-radius: var(--rayon);
        resize: vertical;
      }
    }

    .pied {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .enregistrer {
      min-height: 40px;
      padding: 0.45rem 0.9rem;
      font: inherit;
      font-size: var(--t-md);
      font-weight: 500;
      color: #fff;
      background: var(--bleu-nuit);
      border: 0;
      border-radius: var(--rayon);
      cursor: pointer;

      &:disabled {
        opacity: 0.55;
      }
    }

    .confirme {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      font-size: var(--t-sm);
      color: var(--vert);
    }

    .erreur {
      margin: 0.5rem 0 0;
      font-size: var(--t-sm);
      color: #8c2f2f;
    }
  `,
})
export class BoutonFavoriComponent {
  readonly articleId = input.required<number>();

  protected readonly auth = inject(AuthService);
  private readonly favoris = inject(FavorisService);

  protected readonly marque = signal(false);
  protected readonly note = signal('');
  protected readonly occupe = signal(false);
  protected readonly enregistre = signal(false);
  protected readonly erreur = signal<string | null>(null);

  constructor() {
    // L'état suit l'article affiché : passer à l'article suivant sans
    // recharger laisserait sinon le bouton dans l'état du précédent.
    // `allowSignalWrites` par prudence : `charger` écrit `marque` et
    // `note`. Ces écritures surviennent après un `await`, donc hors du
    // contexte réactif — mais un jour où l'une d'elles remonterait
    // avant l'attente, l'effet lèverait NG0600 et le bouton
    // disparaîtrait sans message. Le coût de l'option est nul.
    effect(
      () => {
        const id = this.articleId();
        if (!this.auth.connecte()) return;
        void this.charger(id);
      },
      { allowSignalWrites: true },
    );
  }

  private async charger(id: number): Promise<void> {
    try {
      const favori = await this.favoris.etat(id);
      this.marque.set(favori !== null);
      this.note.set(favori?.note ?? '');
    } catch {
      // Un état de favori indisponible ne doit pas empêcher de lire
      // l'article : le bouton reste simplement au repos.
      this.marque.set(false);
      this.note.set('');
    }
  }

  protected async basculer(): Promise<void> {
    this.erreur.set(null);
    this.enregistre.set(false);
    this.occupe.set(true);
    try {
      if (this.marque()) {
        await this.favoris.retirer(this.articleId());
        this.marque.set(false);
        this.note.set('');
      } else {
        await this.favoris.enregistrer(this.articleId(), null);
        this.marque.set(true);
      }
    } catch (erreur) {
      this.erreur.set(this.favoris.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  protected async enregistrerNote(): Promise<void> {
    this.erreur.set(null);
    this.occupe.set(true);
    try {
      await this.favoris.enregistrer(this.articleId(), this.note() || null);
      this.enregistre.set(true);
    } catch (erreur) {
      this.erreur.set(this.favoris.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }
}
