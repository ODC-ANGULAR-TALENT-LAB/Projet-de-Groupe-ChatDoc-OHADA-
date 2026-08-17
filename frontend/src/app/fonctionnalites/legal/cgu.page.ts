import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * Conditions générales d'utilisation.
 *
 * ELLES DISENT CE QUE LE PRODUIT REFUSE DE PROMETTRE. Le cahier des
 * charges (§3) range hors périmètre la garantie de conformité et le
 * conseil juridique ; ces conditions le disent à l'utilisateur avant
 * qu'il s'inscrive, pas dans une note de bas de page découverte après.
 *
 * PAGE PUBLIQUE. On doit pouvoir les lire AVANT de créer un compte —
 * des conditions qu'il faudrait accepter pour pouvoir les lire seraient
 * une plaisanterie.
 *
 * LA VERSION EST AFFICHÉE. C'est elle qui est enregistrée sur le compte
 * au moment de l'acceptation ; sans elle, personne ne peut savoir à
 * quel texte il a consenti.
 */
@Component({
  selector: 'app-cgu',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './cgu.page.html',
  styleUrl: './cgu.page.scss',
})
export class CguPage {
  protected readonly version = '2026-08';
}
