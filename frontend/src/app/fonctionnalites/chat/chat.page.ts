import { Component, ElementRef, effect, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ChatService } from '../../core/services/chat.service';
import { AuthService } from '../../core/services/auth.service';
import { BulleMessageComponent } from './composants/bulle-message.component';
import { IconeComponent } from '../../partage/composants/icone.component';

/** Exemples affichés tant que le fil est vide. */
const EXEMPLES = [
  "Combien d'associés minimum dans une SARL ?",
  "Quel est le délai de convocation d'une assemblée générale de SARL ?",
  'Quel est le capital social minimum d’une société anonyme ?',
];

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [FormsModule, RouterLink, BulleMessageComponent, IconeComponent],
  template: `
    <section class="page">
      @if (!auth.connecte()) {
        <!-- La connexion vit sur la page Compte : un seul formulaire
             dans l'application, un seul endroit à maintenir. -->
        <div class="acces">
          <h2>Poser une question</h2>
          <p class="intro">
            Chaque réponse cite l'article officiel qui la fonde, et
            l'assistant refuse explicitement quand le corpus ne permet pas
            de répondre.
          </p>
          <p class="intro">5 questions par mois, gratuitement.</p>
          <a routerLink="/connexion" class="principal lien-bouton">
            Se connecter ou créer un compte
          </a>
          <p class="intro">
            La <a routerLink="/bibliotheque">bibliothèque</a> reste
            consultable sans compte.
          </p>
        </div>
      } @else {
        <header class="entete">
          <h1>Poser une question</h1>
          @if (auth.quota(); as quota) {
            <span class="quota" [class.epuise]="quota.quota_restant === 0">
              {{ quota.quota_restant }} question{{ quota.quota_restant > 1 ? 's' : '' }}
              restante{{ quota.quota_restant > 1 ? 's' : '' }}
            </span>
          }
        </header>

        <div class="fil" #fil>
          @if (!chat.messages().length) {
            <div class="accueil">
              <h2>Que dit le texte ?</h2>
              <p>Posez votre question en français courant. Chaque réponse cite
                 l'article officiel qui la fonde — et l'assistant refuse
                 explicitement quand le corpus ne permet pas de répondre.</p>
              <ul class="exemples">
                @for (exemple of exemples; track exemple) {
                  <li>
                    <button type="button" (click)="question.set(exemple)">
                      {{ exemple }}
                    </button>
                  </li>
                }
              </ul>
            </div>
          }

          @for (message of chat.messages(); track $index) {
            <app-bulle-message [message]="message" />
          }

          <!-- État de chargement explicite : une réponse peut prendre
               jusqu'à 10 secondes, l'utilisateur doit voir qu'il se
               passe quelque chose. -->
          @if (chat.enCours()) {
            <p class="attente" role="status">
              <span class="point"></span><span class="point"></span><span class="point"></span>
              Recherche dans le corpus…
            </p>
          }

          @if (chat.erreur()) {
            <p class="erreur" role="alert">{{ chat.erreur() }}</p>
          }
        </div>

        <div class="composeur">
          <form class="saisie" (ngSubmit)="envoyer()">
            <label class="invisible" for="question">Votre question</label>
            <textarea
              id="question"
              name="question"
              rows="1"
              placeholder="Votre question juridique…"
              [(ngModel)]="questionModele"
              (keydown.enter)="surEntree($event)"
            ></textarea>
            <button
              type="submit"
              class="envoyer"
              [disabled]="chat.enCours() || !question().trim()"
              [attr.aria-label]="chat.enCours() ? 'Envoi en cours' : 'Envoyer la question'"
            >
              <app-icone nom="envoyer" />
            </button>
          </form>
          <!-- Mention obligatoire, discrète mais toujours visible : la
               vérification reste l'affaire du professionnel. -->
          <p class="mention">
            L'assistant peut se tromper. Vérifiez toujours l'article cité.
          </p>
        </div>
      }
    </section>
  `,
  styleUrl: './chat.page.scss',
})
export class ChatPage {
  protected readonly chat = inject(ChatService);
  protected readonly auth = inject(AuthService);

  protected readonly exemples = EXEMPLES;
  protected readonly question = signal('');

  private readonly fil = viewChild<ElementRef<HTMLElement>>('fil');
  private readonly route = inject(ActivatedRoute);

  /** Pont entre le signal et ngModel, qui attend une propriété simple. */
  protected get questionModele(): string {
    return this.question();
  }
  protected set questionModele(valeur: string) {
    this.question.set(valeur);
  }

  constructor() {
    void this.auth.rafraichirQuota();

    // Question arrivée depuis l'accueil (?q=…). Elle est préremplie, pas
    // envoyée : l'utilisateur garde la main pour la reformuler, et une
    // question ne part jamais sans qu'il l'ait voulu — ce qui compte
    // quand chaque envoi décompte le quota.
    const venueDeLAccueil = this.route.snapshot.queryParamMap.get('q');
    if (venueDeLAccueil) this.question.set(venueDeLAccueil);

    // Le fil suit la conversation sans que l'utilisateur ait à défiler.
    effect(() => {
      this.chat.messages();
      this.chat.enCours();
      queueMicrotask(() => {
        const element = this.fil()?.nativeElement;
        if (element) element.scrollTop = element.scrollHeight;
      });
    });
  }

  protected envoyer(): void {
    const texte = this.question();
    this.question.set('');
    void this.chat.poser(texte);
  }

  /** Entrée envoie, Maj+Entrée passe à la ligne. */
  protected surEntree(evenement: Event): void {
    const clavier = evenement as KeyboardEvent;
    if (clavier.shiftKey) return;
    evenement.preventDefault();
    this.envoyer();
  }
}
