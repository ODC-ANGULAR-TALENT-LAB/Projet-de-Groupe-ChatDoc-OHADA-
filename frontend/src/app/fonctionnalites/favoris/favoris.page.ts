import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { Favori, FavorisService } from '../../core/services/favoris.service';
import { IconeComponent } from '../../partage/composants/icone.component';

/**
 * Mes favoris et ma veille.
 *
 * UNE SEULE PAGE POUR LES DEUX, ET C'EST LE POINT. Un favori n'est pas
 * un signet : sa valeur vient de ce qu'il permet de PRÉVENIR quand le
 * texte suivi bouge. Séparer « mes favoris » et « mes alertes » ferait
 * deux listes des mêmes articles, et l'utilisateur devrait faire le
 * rapprochement lui-même.
 *
 * ON SIGNALE, ON NE RÉSUME PAS. L'alerte dit qu'un article a changé et
 * renvoie à son texte. Écrire « le taux est passé de X à Y » sans
 * l'avoir vérifié serait exactement le genre d'affirmation que ce
 * produit refuse de produire.
 */
@Component({
  selector: 'app-favoris',
  standalone: true,
  imports: [RouterLink, IconeComponent],
  templateUrl: './favoris.page.html',
  styleUrl: './favoris.page.scss',
})
export class FavorisPage {
  protected readonly auth = inject(AuthService);
  private readonly service = inject(FavorisService);

  protected readonly favoris = signal<Favori[]>([]);
  protected readonly chargement = signal(true);
  protected readonly erreur = signal<string | null>(null);

  /** Ceux qui ont bougé, en tête : c'est ce qui demande une action. */
  protected readonly aRevoir = computed(() =>
    this.favoris().filter((f) => f.texte_revise || f.article_abroge),
  );

  protected readonly inchanges = computed(() =>
    this.favoris().filter((f) => !f.texte_revise && !f.article_abroge),
  );

  constructor() {
    void this.charger();
  }

  private async charger(): Promise<void> {
    if (!this.auth.connecte()) {
      this.chargement.set(false);
      return;
    }
    try {
      this.favoris.set(await this.service.lister());
      void this.service.rafraichirAlertes();
    } catch (erreur) {
      this.erreur.set(this.service.message(erreur));
    } finally {
      this.chargement.set(false);
    }
  }

  protected async retirer(articleId: number): Promise<void> {
    try {
      await this.service.retirer(articleId);
      this.favoris.update((liste) =>
        liste.filter((f) => f.article_id !== articleId),
      );
    } catch (erreur) {
      this.erreur.set(this.service.message(erreur));
    }
  }
}
