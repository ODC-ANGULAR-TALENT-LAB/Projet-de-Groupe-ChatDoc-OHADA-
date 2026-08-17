import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';

/**
 * Compte et quota.
 *
 * Le quota affiché vient toujours du serveur : rien n'est décompté ici.
 * Un compteur tenu par le navigateur ne protégerait de rien et
 * donnerait un chiffre faux dès qu'un second onglet est ouvert.
 */
@Component({
  selector: 'app-compte',
  standalone: true,
  imports: [RouterLink],
  template: `
    <section class="page">
      <header>
        <h1>Compte</h1>
      </header>

      @if (!auth.connecte()) {
        <!--
          La connexion a sa propre page depuis que l'application en
          possède une. Dupliquer le formulaire ici ferait deux endroits
          à corriger, et l'utilisateur ne saurait pas lequel fait foi.
        -->
        <p class="intro">
          Cette page affiche votre quota et vos données. Elle demande un
          compte.
        </p>
        <div class="actions">
          <a class="principal" routerLink="/connexion">Se connecter</a>
          <a class="secondaire" routerLink="/inscription">Créer un compte</a>
        </div>
      } @else {
        @if (auth.quota(); as quota) {
          <dl class="quota">
            <div>
              <dt>Questions restantes</dt>
              <dd class="chiffre" [class.epuise]="quota.quota_restant === 0">
                {{ quota.quota_restant }}
              </dd>
            </div>
            <div>
              <dt>Plan</dt>
              <dd>{{ quota.plan }}</dd>
            </div>
            @if (quota.quota_reinit_le) {
              <div>
                <dt>Dernière réinitialisation</dt>
                <dd>{{ quota.quota_reinit_le }}</dd>
              </div>
            }
          </dl>

          <p class="aide">
            Le quota se réinitialise au début de chaque mois. Les questions
            auxquelles l'assistant refuse de répondre ne sont pas décomptées.
          </p>
        } @else {
          <p class="attente" role="status">Chargement du quota…</p>
        }

        <section class="confidentialite">
          <h2>Vos données</h2>
          <p>
            Le contenu de vos questions n'est conservé que dans votre
            historique, visible de vous seul. Vous pouvez effacer chaque
            conversation à tout moment depuis
            <a routerLink="/historique">l'historique</a>.
          </p>
        </section>

        <button type="button" class="secondaire" (click)="auth.deconnexion()">
          Se déconnecter
        </button>
      }
    </section>
  `,
  styleUrl: './compte.page.scss',
})
export class ComptePage {
  protected readonly auth = inject(AuthService);

  constructor() {
    void this.auth.rafraichirQuota();
  }
}
