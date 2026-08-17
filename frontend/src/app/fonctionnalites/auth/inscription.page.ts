import {
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { ErreurApi } from '../../core/services/api.service';
import { GoogleService } from '../../core/services/google.service';
import { IconeComponent } from '../../partage/composants/icone.component';

/** Longueur exigée par le serveur. Répétée ici pour prévenir AVANT
    l'envoi : un refus après coup fait ressaisir le formulaire. */
const LONGUEUR_MINIMALE = 8;

/**
 * Création de compte.
 *
 * LA VALIDATION SE FAIT AU DÉPART DU CHAMP, PAS À CHAQUE FRAPPE.
 * Afficher « trop court » dès la première lettre du mot de passe est
 * une réprimande adressée à quelqu'un qui n'a pas fini de répondre.
 */
@Component({
  selector: 'app-inscription',
  standalone: true,
  imports: [FormsModule, RouterLink, IconeComponent],
  templateUrl: './inscription.page.html',
  styleUrl: './authentification.scss',
})
export class InscriptionPage {
  protected readonly auth = inject(AuthService);
  protected readonly google = inject(GoogleService);
  private readonly router = inject(Router);

  protected readonly erreur = signal<string | null>(null);
  protected readonly occupe = signal(false);

  protected readonly email = signal('');
  protected readonly motDePasse = signal('');
  /** Passe à vrai quand l'utilisateur quitte le champ mot de passe. */
  protected readonly motDePasseTouche = signal(false);

  /** Acceptation des conditions. Obligatoire, et revérifiée côté
      serveur : la case informe, elle ne protège pas. */
  protected readonly cguAcceptees = signal(false);

  protected readonly longueurMinimale = LONGUEUR_MINIMALE;

  protected readonly motDePasseTropCourt = computed(
    () =>
      this.motDePasseTouche() &&
      this.motDePasse().length > 0 &&
      this.motDePasse().length < LONGUEUR_MINIMALE,
  );

  protected readonly peutEnvoyer = computed(
    () =>
      !this.occupe() &&
      this.email().includes('@') &&
      this.motDePasse().length >= LONGUEUR_MINIMALE &&
      this.cguAcceptees(),
  );

  protected readonly avantages = [
    '5 questions par mois, sans carte bancaire',
    'Historique, favoris et annotations privées',
    'Alerte quand un article que vous suivez change',
  ];

  private readonly boutonGoogle =
    viewChild<ElementRef<HTMLElement>>('boutonGoogle');

  constructor() {
    if (this.auth.connecte()) {
      void this.router.navigate(['/accueil'], { replaceUrl: true });
      return;
    }

    effect(() => {
      const hote = this.boutonGoogle()?.nativeElement;
      if (!hote || this.auth.connecte()) return;
      void this.google.afficherBouton(hote, (jeton) => this.entrerGoogle(jeton));
    });
  }

  private async entrerGoogle(jetonIdentite: string): Promise<void> {
    this.erreur.set(null);
    this.occupe.set(true);
    try {
      await this.auth.connexionGoogle(jetonIdentite);
      await this.router.navigate(['/accueil']);
    } catch (erreur) {
      this.erreur.set(
        erreur instanceof ErreurApi
          ? erreur.message
          : 'La connexion Google a échoué.',
      );
    } finally {
      this.occupe.set(false);
    }
  }

  protected async creer(): Promise<void> {
    this.erreur.set(null);
    this.occupe.set(true);
    try {
      await this.auth.inscription(
        this.email(),
        this.motDePasse(),
        this.cguAcceptees(),
      );
      this.motDePasse.set('');
      await this.router.navigate(['/accueil']);
    } catch (erreur) {
      this.erreur.set(
        erreur instanceof ErreurApi
          ? erreur.message
          : 'La création du compte a échoué.',
      );
    } finally {
      this.occupe.set(false);
    }
  }
}
