import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import {
  Profil,
  ProfilService,
  ReglePreference,
} from '../../core/services/profil.service';
import { IconeComponent } from '../../partage/composants/icone.component';

interface Reglage {
  cle: string;
  libelle: string;
  explication: string;
  regle: ReglePreference;
}

/**
 * Profil et paramètres.
 *
 * LA LISTE DES RÉGLAGES VIENT DU SERVEUR. Elle est lue sur
 * `/moi/preferences/catalogue`, si bien qu'un réglage ajouté côté
 * serveur apparaît ici sans qu'on touche à ce fichier — et surtout, les
 * deux ne peuvent pas diverger. Seuls le libellé et l'explication sont
 * écrits ici : ce sont des choix de rédaction, pas des données.
 *
 * L'ENREGISTREMENT EST EXPLICITE. Un formulaire qui sauvegarde à chaque
 * frappe empêche de se raviser, et fait douter de ce qui a été retenu.
 */
@Component({
  selector: 'app-parametres',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, IconeComponent],
  templateUrl: './parametres.page.html',
  styleUrl: './parametres.page.scss',
})
export class ParametresPage {
  protected readonly auth = inject(AuthService);
  private readonly service = inject(ProfilService);

  protected readonly profil = signal<Profil | null>(null);
  protected readonly reglages = signal<Reglage[]>([]);

  protected readonly prenom = signal('');
  protected readonly valeurs = signal<Record<string, boolean | string>>({});

  protected readonly chargement = signal(true);
  protected readonly occupe = signal(false);
  protected readonly erreur = signal<string | null>(null);
  protected readonly enregistre = signal(false);

  /** Libellés des réglages. Le serveur dit lesquels existent ; ce
      tableau dit comment les présenter. */
  private readonly REDACTION: Record<string, { libelle: string; explication: string }> = {
    salutation: {
      libelle: 'Me saluer par mon prénom',
      explication:
        "L'accueil et l'assistant s'adressent à vous par votre prénom. Décoché, votre prénom n'est pas transmis à l'assistant.",
    },
    veille_active: {
      libelle: 'Alertes de veille',
      explication:
        'Être prévenu quand un texte portant un article que vous suivez est révisé.',
    },
    format_export: {
      libelle: 'Format proposé en premier',
      explication:
        'Pour les réponses sourcées et les documents générés. Le PDF se transmet, le Word se retouche.',
    },
    extraits_entiers: {
      libelle: 'Extraits officiels entiers',
      explication:
        "Afficher l'article complet plutôt que tronqué dans les listes. Plus long à lire, mais rien n'échappe.",
    },
    densite: {
      libelle: 'Densité de lecture',
      explication:
        'Compacte affiche plus de contenu à l\'écran, confortable espace davantage.',
    },
  };

  constructor() {
    void this.charger();
  }

  private async charger(): Promise<void> {
    if (!this.auth.connecte()) {
      this.chargement.set(false);
      return;
    }
    try {
      await this.service.charger();
      const profil = this.service.profil();
      this.profil.set(profil);
      this.prenom.set(profil?.prenom ?? '');
      this.valeurs.set({ ...(profil?.preferences ?? {}) });

      const catalogue = await this.service.catalogue();
      this.reglages.set(
        Object.entries(catalogue).map(([cle, regle]) => ({
          cle,
          libelle: this.REDACTION[cle]?.libelle ?? cle,
          explication: this.REDACTION[cle]?.explication ?? '',
          regle,
        })),
      );
    } catch (erreur) {
      this.erreur.set(this.service.message(erreur));
    } finally {
      this.chargement.set(false);
    }
  }

  protected changer(cle: string, valeur: boolean | string): void {
    this.valeurs.update((v) => ({ ...v, [cle]: valeur }));
    this.enregistre.set(false);
  }

  protected async enregistrer(): Promise<void> {
    this.erreur.set(null);
    this.enregistre.set(false);
    this.occupe.set(true);
    try {
      const profil = await this.service.enregistrer({
        // Chaîne vide plutôt que null : elle EFFACE le prénom, alors que
        // null signifierait « ne touche pas à ce champ ».
        prenom: this.prenom().trim(),
        preferences: this.valeurs(),
      });
      this.profil.set(profil);
      this.prenom.set(profil.prenom ?? '');
      this.enregistre.set(true);
    } catch (erreur) {
      this.erreur.set(this.service.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }
}
