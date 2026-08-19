import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Avis, AvisService } from '../../core/services/avis.service';
import { AuthService } from '../../core/services/auth.service';
import { IconeComponent } from '../../partage/composants/icone.component';

/**
 * Avis de l'utilisateur sur l'application.
 *
 * UN AVIS UNIQUE, RÉVISABLE. La page sert indifféremment à déposer et à
 * modifier : c'est le même geste, « voici ce que je pense aujourd'hui ».
 * Seul le libellé du bouton change, pour que l'utilisateur sache lequel
 * des deux il est en train de faire.
 *
 * LA NOTE SUFFIT. Le commentaire est facultatif, et le bouton
 * s'active dès qu'une note est choisie : exiger un texte ferait
 * renoncer ceux qui n'ont qu'une impression à livrer, c'est-à-dire la
 * plupart. Une note sans commentaire reste une information ; un
 * formulaire abandonné n'en est pas une.
 */
@Component({
  selector: 'app-avis',
  standalone: true,
  imports: [FormsModule, RouterLink, DatePipe, IconeComponent],
  templateUrl: './avis.page.html',
  styleUrl: './avis.page.scss',
})
export class AvisPage {
  protected readonly auth = inject(AuthService);
  private readonly avis = inject(AvisService);

  protected readonly valeurs = [1, 2, 3, 4, 5];

  /** Ce que vaut chaque étoile, dit en toutes lettres.
   *
   *  Une note nue se lit mal : « 3 » ne veut rien dire tant qu'on ne
   *  sait pas si l'échelle va jusqu'à 5 ou 10, ni si le milieu est
   *  bon ou tiède. Le libellé sert aussi de nom accessible à chaque
   *  bouton radio. */
  protected readonly libelles = [
    'Décevant',
    'Peut mieux faire',
    'Correct',
    'Bon outil',
    'Indispensable',
  ];

  protected readonly note = signal(0);
  protected readonly commentaire = signal('');
  protected readonly existant = signal<Avis | null>(null);
  protected readonly charge = signal(true);
  protected readonly occupe = signal(false);
  protected readonly enregistre = signal(false);
  protected readonly erreur = signal<string | null>(null);

  constructor() {
    void this.charger();
  }

  private async charger(): Promise<void> {
    if (!this.auth.connecte()) {
      this.charge.set(false);
      return;
    }
    try {
      const mien = await this.avis.mien();
      if (mien) {
        this.existant.set(mien);
        this.note.set(mien.note);
        this.commentaire.set(mien.commentaire ?? '');
      }
    } catch (erreur) {
      this.erreur.set(this.avis.message(erreur));
    } finally {
      this.charge.set(false);
    }
  }

  protected async enregistrer(): Promise<void> {
    if (!this.note()) return;

    this.erreur.set(null);
    this.enregistre.set(false);
    this.occupe.set(true);
    try {
      const enregistre = await this.avis.enregistrer(
        this.note(),
        this.commentaire().trim() || null,
      );
      this.existant.set(enregistre);
      this.enregistre.set(true);
    } catch (erreur) {
      this.erreur.set(this.avis.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  protected async retirer(): Promise<void> {
    this.erreur.set(null);
    this.enregistre.set(false);
    this.occupe.set(true);
    try {
      await this.avis.retirer();
      this.existant.set(null);
      this.note.set(0);
      this.commentaire.set('');
    } catch (erreur) {
      this.erreur.set(this.avis.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }
}
