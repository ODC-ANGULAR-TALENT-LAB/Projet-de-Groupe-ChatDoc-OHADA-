import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { ChatService } from '../../core/services/chat.service';
import { HistoriqueService } from '../../core/services/historique.service';

/**
 * Historique des conversations : reprise et effacement.
 *
 * L'effacement est un engagement de confidentialité — un juriste qui
 * interroge sur une procédure collective révèle une information
 * sensible, et doit pouvoir la retirer. La confirmation se fait en
 * ligne, sans boîte de dialogue du navigateur : le geste reste dans la
 * page, à côté de ce qu'il détruit.
 */
@Component({
  selector: 'app-historique',
  standalone: true,
  template: `
    <section class="page">
      <header>
        <h1>Historique</h1>
        <p class="intro">
          Vos conversations passées. Elles ne sont conservées que pour vous, et
          vous pouvez les effacer à tout moment.
        </p>
      </header>

      @if (!auth.connecte()) {
        <p class="vide">Connectez-vous pour retrouver vos conversations.</p>
      } @else if (erreur()) {
        <p class="erreur" role="alert">{{ erreur() }}</p>
      } @else if (historique.conversations() === null) {
        <p class="attente" role="status">Chargement…</p>
      } @else if (!historique.conversations()!.length) {
        <p class="vide">
          Aucune conversation pour l'instant. Vos échanges apparaîtront ici.
        </p>
      } @else {
        <ul class="liste">
          @for (conversation of historique.conversations(); track conversation.id) {
            <li class="conversation">
              <button
                type="button"
                class="reprise"
                [disabled]="reprisEnCours() === conversation.id"
                (click)="reprendre(conversation.id)"
              >
                <span class="titre">
                  {{ conversation.titre || 'Conversation sans titre' }}
                </span>
                <span class="date">{{ formaterDate(conversation.cree_le) }}</span>
              </button>

              @if (aConfirmer() === conversation.id) {
                <div class="confirmation" role="group"
                     aria-label="Confirmer l'effacement">
                  <span>Effacer définitivement ?</span>
                  <button type="button" class="detruire"
                          (click)="effacer(conversation.id)">
                    Effacer
                  </button>
                  <button type="button" class="lien" (click)="aConfirmer.set(null)">
                    Annuler
                  </button>
                </div>
              } @else {
                <button
                  type="button"
                  class="lien effacer"
                  [attr.aria-label]="'Effacer : ' + (conversation.titre || 'conversation')"
                  (click)="aConfirmer.set(conversation.id)"
                >
                  Effacer
                </button>
              }
            </li>
          }
        </ul>
      }
    </section>
  `,
  styleUrl: './historique.page.scss',
})
export class HistoriquePage {
  protected readonly historique = inject(HistoriqueService);
  protected readonly auth = inject(AuthService);
  private readonly chat = inject(ChatService);
  private readonly router = inject(Router);

  protected readonly erreur = signal<string | null>(null);
  protected readonly aConfirmer = signal<number | null>(null);
  protected readonly reprisEnCours = signal<number | null>(null);

  constructor() {
    void this.charger();
  }

  protected formaterDate(iso: string): string {
    return new Date(iso).toLocaleDateString('fr-FR', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  }

  protected async reprendre(id: number): Promise<void> {
    this.reprisEnCours.set(id);
    try {
      this.chat.reprendre(await this.historique.detail(id));
      await this.router.navigate(['/chat']);
    } catch {
      this.erreur.set("Cette conversation n'a pas pu être ouverte.");
    } finally {
      this.reprisEnCours.set(null);
    }
  }

  protected async effacer(id: number): Promise<void> {
    this.aConfirmer.set(null);
    try {
      await this.historique.effacer(id);
      // Le fil affiché devient orphelin si c'était la conversation
      // ouverte : on le remet à zéro plutôt que de laisser l'utilisateur
      // écrire dans une conversation qui n'existe plus.
      if (this.chat.conversationId() === id) this.chat.nouvelleConversation();
    } catch {
      this.erreur.set("L'effacement a échoué.");
    }
  }

  private async charger(): Promise<void> {
    if (!this.auth.connecte()) return;
    try {
      await this.historique.charger();
    } catch {
      this.erreur.set("L'historique n'a pas pu être chargé.");
    }
  }
}
