import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  Calculateur,
  CalculateursService,
  ResultatCalcul,
} from '../../core/services/calculateurs.service';
import { AuthService } from '../../core/services/auth.service';
import { IconeComponent } from '../../partage/composants/icone.component';

/**
 * Calculateurs fiscaux reliés aux articles du Code général des impôts.
 *
 * LE RÉSULTAT N'EST PAS UN CHIFFRE, C'EST UNE PIÈCE DE TRAVAIL. La user
 * story du cahier des charges le dit : « calculer un IS avec le détail
 * des articles appliqués afin de justifier le calcul ». Chaque ligne
 * portant un taux montre donc l'article qui le fonde et son extrait
 * officiel — c'est ce qui distingue cet outil d'une calculatrice.
 *
 * UN CALCULATEUR SANS BASE LÉGALE EST ANNONCÉ COMME TEL, avant la
 * saisie. Laisser l'utilisateur remplir un formulaire pour lui opposer
 * ensuite un refus serait lui faire perdre son temps deux fois.
 */
@Component({
  selector: 'app-calculateurs',
  standalone: true,
  imports: [FormsModule, RouterLink, IconeComponent],
  templateUrl: './calculateurs.page.html',
  styleUrl: './calculateurs.page.scss',
})
export class CalculateursPage {
  protected readonly auth = inject(AuthService);
  private readonly service = inject(CalculateursService);

  protected readonly outils = signal<Calculateur[]>([]);
  protected readonly choisi = signal<string>('tva');
  protected readonly montant = signal<string>('');
  protected readonly surTtc = signal(false);
  /** Taille de l'entreprise, pour la patente uniquement. */
  protected readonly categorie = signal<'grande' | 'moyenne' | 'petite'>(
    'moyenne',
  );

  protected readonly resultat = signal<ResultatCalcul | null>(null);
  protected readonly erreur = signal<string>('');
  protected readonly occupe = signal(false);

  /** Le calculateur actif, pour afficher son état de base légale. */
  protected readonly actif = computed(() =>
    this.outils().find((o) => o.cle === this.choisi()),
  );

  constructor() {
    void this.charger();
  }

  private async charger(): Promise<void> {
    try {
      this.outils.set(await this.service.lister());
    } catch (erreur) {
      this.erreur.set(this.service.message(erreur));
    }
  }

  protected selectionner(cle: string): void {
    this.choisi.set(cle);
    // Un résultat appartient au calculateur qui l'a produit : le garder
    // affiché sous un autre onglet le ferait lire comme le sien.
    this.resultat.set(null);
    this.erreur.set('');
  }

  protected async calculer(): Promise<void> {
    this.erreur.set('');
    this.resultat.set(null);

    const saisie = this.montant().trim().replace(/\s/g, '').replace(',', '.');
    if (!saisie) {
      this.erreur.set('Saisissez un montant.');
      return;
    }

    this.occupe.set(true);
    try {
      this.resultat.set(await this.liquider(saisie));
    } catch (erreur) {
      this.erreur.set(this.service.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  /** Aiguillage vers le calculateur choisi. Un `switch` plutôt qu'une
      table : chaque calculateur a sa propre signature, et les forcer
      dans une forme commune obligerait à passer des paramètres qui ne
      concernent pas les autres. */
  private async liquider(montant: string): Promise<ResultatCalcul> {
    switch (this.choisi()) {
      case 'tva':
        return this.service.tva(montant, this.surTtc());
      case 'irpp':
        return this.service.impotRevenu(montant);
      case 'patente':
        return this.service.patente(montant, this.categorie());
      default:
        return this.service.impotSocietes(montant);
    }
  }

  /** Libellé du champ de saisie : ce qu'on demande change avec l'impôt. */
  protected libelleBase(): string {
    switch (this.choisi()) {
      case 'tva':
        return 'Montant (FCFA)';
      case 'irpp':
        return 'Revenu net imposable (FCFA)';
      case 'patente':
        return "Chiffre d'affaires du dernier exercice clos (FCFA)";
      default:
        return 'Résultat fiscal (FCFA)';
    }
  }

  /**
   * Montant en francs CFA, groupé par milliers.
   *
   * L'espace insécable évite qu'un montant se coupe en fin de ligne :
   * « 15 000 » sur deux lignes se lit comme deux nombres.
   */
  protected formater(montant: string): string {
    const nombre = Number(montant);
    if (!Number.isFinite(nombre)) return montant;
    return nombre.toLocaleString('fr-FR').replace(/ |\s/g, ' ');
  }
}
