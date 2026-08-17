import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * Avertissement déontologique — PERMANENT ET NON MASQUABLE.
 *
 * Ce n'est pas une mention légale décorative : c'est une caractéristique
 * du produit. Elle est reprise en pied de chaque réponse et dans chaque
 * export. Ne pas ajouter de bouton pour la fermer.
 */
@Component({
  selector: 'app-avertissement-deonto',
  standalone: true,
  imports: [RouterLink],
  template: `
    <p class="avertissement">
      Aide à la recherche documentaire. Ne constitue ni une consultation
      juridique, ni un conseil fiscal. Vérifiez toujours l'article cité.
      <!-- Le renvoi vers la méthodologie est ici plutôt que dans la
           navigation : c'est au moment où l'on lit une réponse qu'on se
           demande d'où elle sort. Et c'est le seul endroit visible depuis
           un téléphone, où les onglets sont déjà au maximum de cinq. -->
      <a routerLink="/methodologie">Comment ça marche</a>
    </p>
  `,
  styles: `
    .avertissement {
      margin: 0;
      font-size: 0.75rem;
      line-height: 1.4;
      color: var(--gris-texte);
      border-top: 1px solid var(--bordure);
      padding-top: 0.5rem;
    }

    a {
      color: var(--or-fonce);
      white-space: nowrap;
    }
  `,
})
export class AvertissementDeontoComponent {}
