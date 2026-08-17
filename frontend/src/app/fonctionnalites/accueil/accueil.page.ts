import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { IconeComponent } from '../../partage/composants/icone.component';

/**
 * Accueil — proposition de valeur et entrée dans le parcours principal.
 *
 * LE CHAMP DE QUESTION EST IMMÉDIAT, avant toute inscription. Le cahier
 * des charges (§7) le demande explicitement, et pour une bonne raison :
 * demander de créer un compte avant d'avoir montré ce que l'outil sait
 * faire, c'est perdre l'utilisateur au moment où il est le plus curieux.
 * La connexion n'est réclamée qu'à l'envoi.
 *
 * LES EXEMPLES SONT RANGÉS PAR PERSONA, repris des profils du §4. Un
 * expert-comptable et un étudiant n'arrivent pas avec la même question :
 * montrer les deux fait comprendre plus vite le périmètre de l'outil
 * qu'un paragraphe d'explication.
 */
interface Persona {
  titre: string;
  besoin: string;
  exemples: string[];
}

const PERSONAS: Persona[] = [
  {
    titre: 'Expert-comptable, DAF',
    besoin: 'Retrouver en secondes la base légale exacte et la citer sans risque.',
    exemples: [
      'Quelles mentions doivent figurer sur une facture commerciale ?',
      "Quel est le délai de dépôt des états financiers au registre du commerce ?",
    ],
  },
  {
    titre: 'Avocat, juriste',
    besoin: 'Vérifier un point de formalisme avec son extrait officiel.',
    exemples: [
      "Quel est le délai de convocation d'une assemblée générale de SARL ?",
      'Comment se constitue une société par actions simplifiée ?',
    ],
  },
  {
    titre: 'Entrepreneur',
    besoin: 'Connaître ses obligations sans payer une consultation.',
    exemples: [
      "Combien d'associés minimum dans une SARL ?",
      "Que risque un commerçant qui ne s'immatricule pas ?",
    ],
  },
];

@Component({
  selector: 'app-accueil',
  standalone: true,
  imports: [FormsModule, RouterLink, IconeComponent],
  template: `
    <section class="page">
      <header class="entete">
        <h1>
          Le droit OHADA, <span class="accent">preuve à l'appui</span>
        </h1>
        <p class="promesse">
          Posez votre question en français courant. Chaque réponse affiche
          l'extrait exact de l'article officiel qui la fonde — et l'assistant
          refuse explicitement quand le corpus ne permet pas de répondre.
        </p>

        <form class="saisie" (ngSubmit)="demarrer()">
          <label class="invisible" for="question-accueil">Votre question</label>
          <input
            id="question-accueil"
            name="question"
            [(ngModel)]="question"
            placeholder="Votre question juridique…"
          />
          <button type="submit" class="envoyer" [disabled]="!question.trim()"
                  aria-label="Poser la question">
            <app-icone nom="envoyer" />
          </button>
        </form>

        @if (!auth.connecte()) {
          <p class="note">
            5 questions par mois, gratuitement. La
            <a routerLink="/bibliotheque">bibliothèque</a> reste consultable
            sans compte.
          </p>
        }
      </header>

      <!-- Ce qui distingue l'outil. Trois garanties mécaniques, pas trois
           promesses commerciales : chacune est vérifiable à l'usage. -->
      <section class="garanties">
        <article>
          <h2>La citation, jamais l'affirmation</h2>
          <p>
            Toute affirmation juridique est adossée à un extrait du corpus.
            Une citation qui ne résiste pas au contrôle fait rejeter la
            réponse entière.
          </p>
        </article>
        <article>
          <h2>Le refus est une fonctionnalité</h2>
          <p>
            Hors du corpus, l'assistant le dit au lieu d'inventer. Savoir
            qu'il ne ment jamais vaut mieux que savoir qu'il répond toujours.
          </p>
        </article>
        <article>
          <h2>Un corpus daté et traçable</h2>
          <p>
            Chaque texte porte sa version, sa source officielle et le nom de
            qui l'a validé.
            <a routerLink="/methodologie">Voir la provenance</a>
          </p>
        </article>
      </section>

      <section class="personas">
        <h2>Par où commencer</h2>
        <div class="grille">
          @for (persona of personas; track persona.titre) {
            <article>
              <h3>{{ persona.titre }}</h3>
              <p class="besoin">{{ persona.besoin }}</p>
              <ul>
                @for (exemple of persona.exemples; track exemple) {
                  <li>
                    <button type="button" (click)="poser(exemple)">
                      {{ exemple }}
                    </button>
                  </li>
                }
              </ul>
            </article>
          }
        </div>
      </section>

      <p class="avertissement">
        ChatDocs OHADA est une aide à la recherche documentaire. Il ne
        constitue ni une consultation juridique, ni un conseil fiscal, ni un
        acte relevant d'une profession réglementée.
        <a routerLink="/methodologie">Limites de l'outil</a>
      </p>
    </section>
  `,
  styleUrl: './accueil.page.scss',
})
export class AccueilPage {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly personas = PERSONAS;
  protected question = '';

  protected demarrer(): void {
    if (this.question.trim()) this.poser(this.question);
  }

  /**
   * Ouvre le chat avec la question déjà écrite.
   *
   * Elle passe par l'URL plutôt que par un service : un lien vers une
   * question devient partageable, et un rechargement ne la perd pas.
   */
  protected poser(question: string): void {
    void this.router.navigate(['/chat'], { queryParams: { q: question } });
  }
}
