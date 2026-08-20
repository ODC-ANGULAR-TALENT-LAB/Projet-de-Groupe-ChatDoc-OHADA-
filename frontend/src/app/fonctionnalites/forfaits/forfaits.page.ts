import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import {
  Abonnement,
  Forfait,
  ForfaitsService,
  Paiement,
} from '../../core/services/forfaits.service';
import { IconeComponent } from '../../partage/composants/icone.component';

/** Toutes les 4 s : assez pour suivre, assez peu pour ne pas marteler. */
const PERIODE_SUIVI = 4000;

/**
 * Deux minutes de suivi, puis on rend la main.
 *
 * Un utilisateur met rarement plus longtemps à composer son code ; au
 * delà, laisser tourner une boucle qui n'aboutira pas donne l'illusion
 * que quelque chose se passe encore.
 */
const TENTATIVES_MAX = 30;

/**
 * Choix du forfait et paiement Mobile Money.
 *
 * LE CATALOGUE S'AFFICHE MÊME SANS COMPTE. Le prix est ce qu'on veut
 * connaître AVANT de s'inscrire ; le cacher obligerait à créer un
 * compte pour savoir ce que coûte le service.
 *
 * AUCUN SECRET DE PAIEMENT NE PASSE PAR CETTE PAGE. On demande un
 * numéro de téléphone — un identifiant, pas un secret — et l'opérateur
 * envoie une invite sur l'appareil de l'abonné, qui y saisit son code.
 * Le champ correspondant n'existe pas ici, et ne doit jamais exister.
 *
 * C'EST LE SERVEUR QUI CONSTATE LE PAIEMENT. Cette page interroge, elle
 * ne décide pas : afficher « payé » sur la foi du navigateur ouvrirait
 * un abonnement à qui saurait modifier une réponse.
 */
@Component({
  selector: 'app-forfaits',
  standalone: true,
  imports: [FormsModule, RouterLink, DatePipe, DecimalPipe, IconeComponent],
  templateUrl: './forfaits.page.html',
  styleUrl: './forfaits.page.scss',
})
export class ForfaitsPage {
  protected readonly auth = inject(AuthService);
  private readonly forfaits = inject(ForfaitsService);
  private readonly destruction = inject(DestroyRef);

  protected readonly catalogue = signal<Forfait[]>([]);
  protected readonly abonnement = signal<Abonnement | null>(null);
  protected readonly charge = signal(true);
  protected readonly occupe = signal(false);
  protected readonly erreur = signal<string | null>(null);

  /** Forfait dont on est en train de régler le paiement. */
  protected readonly enPaiement = signal<Forfait | null>(null);
  protected readonly telephone = signal('');
  protected readonly paiement = signal<Paiement | null>(null);
  protected readonly attenteConfirmation = signal(false);

  private minuteur: ReturnType<typeof setInterval> | null = null;

  constructor() {
    void this.charger();
    // Quitter la page pendant un paiement ne doit pas laisser une
    // boucle interroger le serveur indéfiniment.
    this.destruction.onDestroy(() => this.arreterSuivi());
  }

  private async charger(): Promise<void> {
    try {
      this.catalogue.set(await this.forfaits.catalogue());
      if (this.auth.connecte()) {
        this.abonnement.set(await this.forfaits.mien());
      }
    } catch (erreur) {
      this.erreur.set(this.forfaits.message(erreur));
    } finally {
      this.charge.set(false);
    }
  }

  protected estActuel(code: string): boolean {
    return this.abonnement()?.forfait.code === code;
  }

  protected estDemande(code: string): boolean {
    return this.abonnement()?.demande_en_attente === code;
  }

  protected libelle(code: string): string {
    return this.catalogue().find((f) => f.code === code)?.libelle ?? code;
  }

  protected choisir(forfait: Forfait): void {
    this.erreur.set(null);

    // Le gratuit ne se paie pas : le changement est immédiat.
    if (forfait.prix_fcfa === 0) {
      void this.renoncer();
      return;
    }

    // Sans CamPay configuré, on dépose une demande que l'équipe
    // traitera : mieux vaut cela qu'un bouton qui échoue.
    if (!this.abonnement()?.paiement_mobile) {
      void this.demanderHorsLigne(forfait);
      return;
    }

    this.enPaiement.set(forfait);
    this.paiement.set(null);
  }

  private async renoncer(): Promise<void> {
    this.occupe.set(true);
    try {
      this.abonnement.set(await this.forfaits.demander('gratuit'));
    } catch (erreur) {
      this.erreur.set(this.forfaits.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  private async demanderHorsLigne(forfait: Forfait): Promise<void> {
    this.occupe.set(true);
    try {
      this.abonnement.set(await this.forfaits.demander(forfait.code));
    } catch (erreur) {
      this.erreur.set(this.forfaits.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  protected annulerPaiement(): void {
    this.arreterSuivi();
    this.enPaiement.set(null);
    this.paiement.set(null);
    this.attenteConfirmation.set(false);
  }

  protected async lancerPaiement(): Promise<void> {
    const forfait = this.enPaiement();
    if (!forfait || !this.telephone().trim()) return;

    this.erreur.set(null);
    this.occupe.set(true);
    try {
      this.paiement.set(
        await this.forfaits.payer(forfait.code, this.telephone().trim()),
      );
      this.attenteConfirmation.set(true);
      this.demarrerSuivi();
    } catch (erreur) {
      this.erreur.set(this.forfaits.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  private demarrerSuivi(): void {
    this.arreterSuivi();
    let tentatives = 0;

    this.minuteur = setInterval(async () => {
      tentatives += 1;
      if (tentatives > TENTATIVES_MAX) {
        this.arreterSuivi();
        this.attenteConfirmation.set(false);
        this.erreur.set(
          "Le paiement n'a pas été confirmé. S'il a bien été débité, " +
            'vos crédits s’ouvriront automatiquement ; sinon, réessayez.',
        );
        return;
      }

      try {
        const suivi = await this.forfaits.suivrePaiement();
        this.paiement.set(suivi);

        if (suivi.statut === 'SUCCESSFUL') {
          this.arreterSuivi();
          this.attenteConfirmation.set(false);
          this.enPaiement.set(null);
          // Le serveur renvoie l'abonnement à jour : pas de second appel.
          this.abonnement.set(suivi.abonnement ?? (await this.forfaits.mien()));
        } else if (suivi.statut === 'FAILED') {
          this.arreterSuivi();
          this.attenteConfirmation.set(false);
          this.erreur.set(
            "Le paiement n'a pas abouti. Aucun montant n'a été débité.",
          );
          this.abonnement.set(await this.forfaits.mien());
        }
      } catch {
        // Une lecture ratée n'est pas un échec du paiement : le réseau
        // peut cligner. On laisse la boucle réessayer.
      }
    }, PERIODE_SUIVI);
  }

  private arreterSuivi(): void {
    if (this.minuteur !== null) {
      clearInterval(this.minuteur);
      this.minuteur = null;
    }
  }

  protected async annuler(): Promise<void> {
    this.erreur.set(null);
    this.occupe.set(true);
    try {
      await this.forfaits.annulerDemande();
      this.abonnement.set(await this.forfaits.mien());
    } catch (erreur) {
      this.erreur.set(this.forfaits.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }
}
