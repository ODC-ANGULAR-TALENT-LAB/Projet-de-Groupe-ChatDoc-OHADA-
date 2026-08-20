import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  AdministrationService,
  CompteAdmin,
  Role,
  TableauDeBord,
} from '../../core/services/administration.service';
import { AvisService, SyntheseAvis } from '../../core/services/avis.service';
import {
  DemandeAbonnement,
  Forfait,
  ForfaitsService,
} from '../../core/services/forfaits.service';
import { ProfilService } from '../../core/services/profil.service';
import { IconeComponent } from '../../partage/composants/icone.component';

type Onglet = 'apercu' | 'abonnements' | 'comptes' | 'avis' | 'forfaits';

/**
 * Console d'administration du service.
 *
 * DISTINCTE DE L'ESPACE JURISTE (/admin), et ce n'est pas un doublon.
 * Le juriste tient le CORPUS : il dépose des textes officiels, les
 * relit, les valide, et il en répond — son nom figure dans la table de
 * provenance publiée. L'administrateur tient le SERVICE : comptes,
 * rôles, abonnements, avis. Réunir les deux sous un même écran
 * mélangerait une responsabilité juridique et une responsabilité
 * d'exploitation.
 *
 * ONGLETS PLUTÔT QU'UNE PAGE À DÉROULER. Ces quatre domaines ne se
 * consultent pas ensemble : on vient valider un paiement, ou promouvoir
 * un juriste, ou lire les avis. Les empiler obligerait à parcourir
 * trois sections pour atteindre la quatrième, et le tableau des comptes
 * chasserait tout le reste hors de l'écran.
 *
 * L'APERÇU EST LE PREMIER ONGLET parce qu'il répond à la seule question
 * qu'on se pose en arrivant : « y a-t-il quelque chose à traiter ? ».
 * Le nombre de demandes en attente y est mis en avant pour cette
 * raison — quelqu'un a payé et attend.
 */
@Component({
  selector: 'app-administration',
  standalone: true,
  imports: [FormsModule, RouterLink, DatePipe, DecimalPipe, IconeComponent],
  templateUrl: './administration.page.html',
  styleUrl: './administration.page.scss',
})
export class AdministrationPage {
  private readonly administration = inject(AdministrationService);
  private readonly forfaitsService = inject(ForfaitsService);
  private readonly avisService = inject(AvisService);
  protected readonly profils = inject(ProfilService);

  protected readonly estAdmin = computed(
    () => this.profils.profil()?.role === 'admin',
  );

  protected readonly onglet = signal<Onglet>('apercu');
  protected readonly charge = signal(true);
  protected readonly occupe = signal(false);
  protected readonly erreur = signal<string | null>(null);
  protected readonly confirmation = signal<string | null>(null);

  protected readonly bord = signal<TableauDeBord | null>(null);
  protected readonly comptes = signal<CompteAdmin[]>([]);
  protected readonly demandes = signal<DemandeAbonnement[]>([]);
  protected readonly avis = signal<SyntheseAvis | null>(null);
  protected readonly forfaits = signal<Forfait[]>([]);

  /** Filtre du tableau des comptes : e-mail, prénom ou rôle. */
  protected readonly filtre = signal('');

  protected readonly comptesFiltres = computed(() => {
    const terme = this.filtre().trim().toLowerCase();
    if (!terme) return this.comptes();
    return this.comptes().filter(
      (c) =>
        c.email.toLowerCase().includes(terme) ||
        (c.prenom ?? '').toLowerCase().includes(terme) ||
        c.role.includes(terme) ||
        c.plan.includes(terme),
    );
  });

  protected readonly enAttente = computed(() =>
    this.demandes().filter((d) => d.statut === 'en_attente'),
  );
  protected readonly traitees = computed(() =>
    this.demandes().filter((d) => d.statut !== 'en_attente'),
  );

  /** Saisies de validation, indexées par identifiant de demande. */
  protected readonly references = signal<Record<number, string>>({});
  protected readonly motifs = signal<Record<number, string>>({});

  protected readonly roles: Role[] = ['utilisateur', 'juriste', 'admin'];

  constructor() {
    void this.charger();
  }

  private async charger(): Promise<void> {
    // Le rôle vit dans le profil : sans lui, on ne peut pas savoir si
    // cet écran doit s'afficher. Le serveur refuse de toute façon
    // (403) — ce contrôle sert à montrer un message plutôt qu'une page
    // en erreur.
    if (!this.profils.profil()) {
      try {
        await this.profils.charger();
      } catch {
        // Non connecté : le message d'accès réservé suffit.
      }
    }
    if (!this.estAdmin()) {
      this.charge.set(false);
      return;
    }
    try {
      // En parallèle : quatre appels indépendants, et les enchaîner
      // ferait attendre le plus lent après le plus rapide.
      const [bord, comptes, demandes, avis, forfaits] = await Promise.all([
        this.administration.tableauDeBord(),
        this.administration.comptes(),
        this.forfaitsService.demandes(),
        this.avisService.synthese(),
        this.forfaitsService.catalogue(),
      ]);
      this.bord.set(bord);
      this.comptes.set(comptes);
      this.demandes.set(demandes);
      this.avis.set(avis);
      this.forfaits.set(forfaits);
    } catch (erreur) {
      this.erreur.set(this.administration.message(erreur));
    } finally {
      this.charge.set(false);
    }
  }

  protected libelleForfait(code: string): string {
    return this.forfaits().find((f) => f.code === code)?.libelle ?? code;
  }

  protected reference(id: number): string {
    return this.references()[id] ?? '';
  }

  protected poserReference(id: number, valeur: string): void {
    this.references.update((r) => ({ ...r, [id]: valeur }));
  }

  protected motif(id: number): string {
    return this.motifs()[id] ?? '';
  }

  protected poserMotif(id: number, valeur: string): void {
    this.motifs.update((m) => ({ ...m, [id]: valeur }));
  }

  protected async valider(demande: DemandeAbonnement): Promise<void> {
    const reference = this.reference(demande.id).trim();
    if (reference.length < 3) {
      this.erreur.set(
        'Indiquez la référence du paiement constaté : sans elle, un litige ne se tranche pas.',
      );
      return;
    }
    await this.agir(async () => {
      await this.forfaitsService.valider(demande.id, reference);
      this.confirmation.set(
        `Forfait ${this.libelleForfait(demande.forfait_code)} ouvert à ${demande.email}.`,
      );
    });
  }

  protected async refuser(demande: DemandeAbonnement): Promise<void> {
    const motif = this.motif(demande.id).trim();
    if (motif.length < 3) {
      this.erreur.set(
        'Indiquez un motif : un refus sans raison laisse la personne sans rien pour comprendre.',
      );
      return;
    }
    await this.agir(async () => {
      await this.forfaitsService.refuser(demande.id, motif);
      this.confirmation.set(`Demande de ${demande.email} refusée.`);
    });
  }

  protected async changerRole(compte: CompteAdmin, role: Role): Promise<void> {
    if (role === compte.role) return;
    await this.agir(async () => {
      const modifie = await this.administration.changerRole(compte.id, role);
      this.comptes.update((liste) =>
        liste.map((c) => (c.id === modifie.id ? modifie : c)),
      );
      this.confirmation.set(`${compte.email} est désormais ${role}.`);
    });
  }

  /**
   * Exécute une action, puis recharge.
   *
   * LE RECHARGEMENT N'EST PAS DU CONFORT. Valider un abonnement change
   * le tableau de bord, la liste des demandes ET la ligne du compte
   * concerné. Ne rafraîchir que ce qu'on croit avoir touché laisse un
   * écran qui se contredit lui-même.
   */
  private async agir(action: () => Promise<void>): Promise<void> {
    this.erreur.set(null);
    this.confirmation.set(null);
    this.occupe.set(true);
    try {
      await action();
      const [bord, demandes, comptes] = await Promise.all([
        this.administration.tableauDeBord(),
        this.forfaitsService.demandes(),
        this.administration.comptes(),
      ]);
      this.bord.set(bord);
      this.demandes.set(demandes);
      this.comptes.set(comptes);
    } catch (erreur) {
      this.erreur.set(this.administration.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }
}
