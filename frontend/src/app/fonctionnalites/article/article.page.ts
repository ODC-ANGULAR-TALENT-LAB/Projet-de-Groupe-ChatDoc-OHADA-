import { Component, effect, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Article } from '../../core/models';
import { CorpusService } from '../../core/services/corpus.service';
import { BoutonFavoriComponent } from '../../partage/composants/bouton-favori.component';

/**
 * Lecture d'un article — la cible des citations.
 *
 * Sans cette page, cliquer sur une citation ne mène nulle part et la
 * promesse du produit s'arrête à mi-chemin : l'utilisateur doit pouvoir
 * lire l'article entier, dans son contexte.
 */
@Component({
  selector: 'app-article',
  standalone: true,
  imports: [RouterLink, BoutonFavoriComponent],
  template: `
    <section class="page">
      @if (article(); as article) {
        <!-- Fil d'Ariane complet : acte → livre → titre → chapitre -->
        <nav class="ariane" aria-label="Fil d'Ariane">
          <a routerLink="/chat">Chat</a>
          <span aria-hidden="true">›</span>
          <span>{{ article.texte.sigle }}</span>
          @for (niveau of niveaux(article.chemin); track niveau) {
            <span aria-hidden="true">›</span>
            <span>{{ niveau }}</span>
          }
        </nav>

        <header>
          <h1>Article {{ article.numero }}</h1>
          <p class="texte-source">{{ article.texte.titre }}</p>
        </header>

        <p class="contenu">{{ article.contenu }}</p>

        <!-- Mettre de côté et annoter : le geste appartient à la page
             de lecture, c'est là qu'on décide qu'un article compte. -->
        <app-bouton-favori [articleId]="article.id" />

        <!-- Version et date de consolidation : condition de confiance
             professionnelle, pas un détail d'affichage. -->
        <dl class="provenance">
          <div>
            <dt>Version</dt>
            <dd>{{ article.texte.version }}</dd>
          </div>
          <div>
            <dt>Consolidé au</dt>
            <dd>{{ article.texte.date_consolidation }}</dd>
          </div>
          <div>
            <dt>En vigueur depuis</dt>
            <dd>{{ article.date_entree_vigueur }}</dd>
          </div>
          @if (article.date_abrogation) {
            <div>
              <dt>Abrogé le</dt>
              <dd class="abroge">{{ article.date_abrogation }}</dd>
            </div>
          }
        </dl>

        <nav class="voisins" aria-label="Navigation entre articles">
          @if (article.precedent_id) {
            <a class="secondaire" [routerLink]="['/article', article.precedent_id]">
              ← Article précédent
            </a>
          }
          @if (article.suivant_id) {
            <a class="secondaire suivant" [routerLink]="['/article', article.suivant_id]">
              Article suivant →
            </a>
          }
        </nav>
      } @else if (erreur()) {
        <p class="erreur" role="alert">{{ erreur() }}</p>
        <a routerLink="/chat" class="secondaire">Retour au chat</a>
      } @else {
        <p class="attente" role="status">Chargement de l'article…</p>
      }
    </section>
  `,
  styles: `
    .page {
      max-width: 42rem;
      margin: 0 auto;
      padding: 1rem 0.75rem 3rem;
    }

    .ariane {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      font-size: var(--t-xs);
      color: var(--gris-texte);
      margin-bottom: 1rem;

      a {
        color: var(--bleu-nuit);
      }
    }

    h1 {
      font-family: var(--police-serif);
      font-size: var(--t-2xl);
      margin: 0;
    }

    .texte-source {
      margin: 0.2rem 0 1.25rem;
      font-size: var(--t-md);
      color: var(--gris-texte);
    }

    .contenu {
      font-family: var(--police-serif);
      font-size: var(--t-lg);
      line-height: 1.75;
      white-space: pre-wrap;
      border-left: 3px solid var(--or);
      padding-left: 1rem;
      margin: 0 0 1.75rem;
    }

    .provenance {
      display: flex;
      flex-wrap: wrap;
      gap: 1.25rem;
      margin: 0 0 2rem;
      padding: 0.75rem 0;
      border-top: 1px solid var(--bordure);
      border-bottom: 1px solid var(--bordure);
      font-size: var(--t-sm);

      dt {
        color: var(--gris-texte);
        font-size: var(--t-xs);
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }

      dd {
        margin: 0.15rem 0 0;
        font-weight: 500;
      }

      .abroge {
        color: #9a2a2a;
      }
    }

    .voisins {
      display: flex;
      justify-content: space-between;
      gap: 0.5rem;

      .suivant {
        margin-left: auto;
      }
    }

    .erreur {
      color: #9a2a2a;
    }
  `,
})
export class ArticlePage {
  /** Lié au paramètre de route grâce à withComponentInputBinding(). */
  readonly id = input.required<string>();

  private readonly corpus = inject(CorpusService);

  protected readonly article = signal<Article | null>(null);
  protected readonly erreur = signal<string | null>(null);

  constructor() {
    // input() est un signal : charger dans un effet suit la navigation
    // d'un article vers son voisin, où Angular réutilise le composant
    // au lieu de le recréer. Un chargement au constructeur laisserait
    // l'article précédent affiché.
    //
    // `allowSignalWrites` EST INDISPENSABLE ICI, et son absence rendait
    // la page inutilisable : remettre `article` à null avant de charger
    // est une écriture SYNCHRONE dans un effet, qu'Angular refuse par
    // défaut (NG0600). L'effet levait donc avant même d'appeler l'API —
    // aucune requête n'était émise, et la page restait indéfiniment sur
    // « Chargement de l'article… ».
    //
    // Le symptôme trompe : cela ressemble à une lenteur réseau, alors
    // que rien n'est parti sur le réseau. L'erreur n'apparaît que dans
    // la console du navigateur.
    //
    // La remise à null n'est pas décorative : sans elle, passer d'un
    // article à son voisin afficherait le texte du précédent pendant le
    // chargement du suivant — un contresens dans un outil juridique.
    effect(
      () => {
        const identifiant = Number(this.id());
        this.article.set(null);
        this.erreur.set(null);
        void this.charger(identifiant);
      },
      { allowSignalWrites: true },
    );
  }

  protected niveaux(chemin: string): string[] {
    return chemin ? chemin.split(' > ') : [];
  }

  private async charger(identifiant: number): Promise<void> {
    try {
      this.article.set(await this.corpus.article(identifiant));
    } catch {
      this.erreur.set("Cet article est introuvable.");
    }
  }
}
