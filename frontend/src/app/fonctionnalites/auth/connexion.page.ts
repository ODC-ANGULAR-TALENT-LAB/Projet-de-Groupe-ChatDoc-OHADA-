import {
  Component,
  ElementRef,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { ErreurApi } from '../../core/services/api.service';
import { GoogleService } from '../../core/services/google.service';
import { IconeComponent } from '../../partage/composants/icone.component';

/**
 * Connexion.
 *
 * PAGE DISTINCTE DE L'INSCRIPTION, ET C'EST DÉLIBÉRÉ. Un formulaire
 * unique portant deux boutons — « se connecter » et « créer un compte »
 * — oblige l'utilisateur à choisir son intention APRÈS avoir saisi ses
 * identifiants, et fait échouer le gestionnaire de mots de passe, qui
 * ne sait pas s'il doit proposer un mot de passe existant ou en générer
 * un. Deux pages, deux `autocomplete`, deux intentions claires.
 */
@Component({
  selector: 'app-connexion',
  standalone: true,
  imports: [FormsModule, RouterLink, IconeComponent],
  templateUrl: './connexion.page.html',
  styleUrl: './authentification.scss',
})
export class ConnexionPage {
  protected readonly auth = inject(AuthService);
  protected readonly google = inject(GoogleService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly erreur = signal<string | null>(null);
  protected readonly occupe = signal(false);

  protected email = '';
  protected motDePasse = '';

  protected readonly points = [
    "Chaque réponse cite l'article qui la fonde",
    "L'assistant refuse plutôt que d'inventer",
    'Export PDF sourcé pour vos dossiers',
  ];

  private readonly boutonGoogle =
    viewChild<ElementRef<HTMLElement>>('boutonGoogle');

  constructor() {
    // Arrivée après expiration : l'intercepteur a fermé la session et
    // renvoyé ici. Sans ce message, l'utilisateur se retrouve sur la
    // page de connexion sans savoir ce qu'il a fait de mal — il vient
    // de cliquer sur tout autre chose.
    if (this.route.snapshot.queryParamMap.get('session') === 'expiree') {
      this.erreur.set(
        'Votre session a expiré. Reconnectez-vous pour reprendre où vous en étiez.',
      );
    }

    if (this.auth.connecte()) {
      void this.router.navigate(['/accueil'], { replaceUrl: true });
      return;
    }

    // `allowSignalWrites` : afficherBouton() marque le script Google
    // comme disponible, et cette écriture se produit de façon SYNCHRONE
    // quand le script est déjà chargé. Sans cette option, l'effet lève
    // NG0600 et le bouton n'apparaît jamais — sans autre trace que la
    // console du navigateur.
    effect(
      () => {
        const hote = this.boutonGoogle()?.nativeElement;
        if (!hote || this.auth.connecte()) return;
        void this.google.afficherBouton(hote, (jeton) =>
          this.entrerGoogle(jeton),
        );
      },
      { allowSignalWrites: true },
    );
  }

  private async entrerGoogle(jetonIdentite: string): Promise<void> {
    this.erreur.set(null);
    this.occupe.set(true);
    try {
      await this.auth.connexionGoogle(jetonIdentite);
      await this.router.navigate(['/accueil']);
    } catch (erreur) {
      // CUL-DE-SAC À ÉVITER. Cette page sert à se CONNECTER : elle n'a
      // pas de case « j'accepte les conditions », et n'a pas à en avoir
      // une. Mais le compte Google peut être inconnu — c'est alors une
      // inscription, que le serveur refuse sans acceptation.
      //
      // Sans ce cas, l'utilisateur lisait « les conditions doivent être
      // acceptées » sur une page où rien ne permet de les accepter.
      if (erreur instanceof ErreurApi && erreur.statut === 422) {
        this.erreur.set(null);
        await this.router.navigate(['/inscription'], {
          queryParams: { google: 'nouveau' },
        });
        return;
      }
      this.erreur.set(
        erreur instanceof ErreurApi
          ? erreur.message
          : 'La connexion Google a échoué.',
      );
    } finally {
      this.occupe.set(false);
    }
  }

  protected async entrer(): Promise<void> {
    this.erreur.set(null);
    this.occupe.set(true);
    try {
      await this.auth.connexion(this.email, this.motDePasse);
      this.motDePasse = '';
      await this.router.navigate(['/accueil']);
    } catch (erreur) {
      this.erreur.set(
        erreur instanceof ErreurApi ? erreur.message : 'Connexion impossible.',
      );
    } finally {
      this.occupe.set(false);
    }
  }
}
