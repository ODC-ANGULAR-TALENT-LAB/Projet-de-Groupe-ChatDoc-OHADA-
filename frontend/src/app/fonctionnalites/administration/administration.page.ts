import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  AdministrationService,
  CompteAdmin,
  ForfaitAdmin,
  ForfaitEcriture,
  Role,
  Signalement,
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

type Onglet =
  | 'apercu'
  | 'abonnements'
  | 'signalements'
  | 'comptes'
  | 'avis'
  | 'forfaits';

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
  protected readonly forfaitsAdmin = signal<ForfaitAdmin[]>([]);
  protected readonly signalements = signal<Signalement[]>([]);

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

  protected readonly signalementsOuverts = computed(() =>
    this.signalements().filter((s) => s.statut === 'ouvert'),
  );

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
      const [bord, comptes, demandes, avis, forfaits, catalogue, signalements] =
        await Promise.all([
          this.administration.tableauDeBord(),
          this.administration.comptes(),
          this.forfaitsService.demandes(),
          this.avisService.synthese(),
          this.forfaitsService.catalogue(),
          this.administration.forfaits(),
          this.administration.signalements(),
        ]);
      this.bord.set(bord);
      this.comptes.set(comptes);
      this.demandes.set(demandes);
      this.avis.set(avis);
      this.forfaits.set(forfaits);
      this.forfaitsAdmin.set(catalogue);
      this.signalements.set(signalements);
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

  /**
   * Ce compte est-il le dernier administrateur actif ?
   *
   * LA RÈGLE EST CELLE DU SERVEUR, reproduite ici pour GRISER les
   * actions plutôt que de les laisser échouer en 409. Le serveur reste
   * seul juge : cette copie n'autorise rien, elle évite seulement de
   * proposer un geste impossible.
   */
  protected estDernierAdmin(compte: CompteAdmin): boolean {
    if (compte.role !== 'admin') return false;
    return (
      this.comptes().filter((c) => c.role === 'admin' && !c.suspendu_le)
        .length <= 1
    );
  }

  /** Le compte de l'administrateur connecté. */
  protected estMoi(compte: CompteAdmin): boolean {
    return compte.email === this.profils.profil()?.email;
  }

  protected verrouille(compte: CompteAdmin): boolean {
    return this.estMoi(compte) || this.estDernierAdmin(compte);
  }

  protected readonly suspension = signal<number | null>(null);
  protected readonly motifSuspension = signal('');

  protected ouvrirSuspension(compte: CompteAdmin): void {
    this.erreur.set(null);
    this.confirmation.set(null);
    this.suspension.set(compte.id);
    this.motifSuspension.set('');
  }

  protected async suspendre(compte: CompteAdmin): Promise<void> {
    const motif = this.motifSuspension().trim();
    if (motif.length < 3) {
      this.erreur.set(
        'Indiquez la raison : sans elle, celui qui lèvera la suspension ne saura pas ce qu’il lève.',
      );
      return;
    }
    await this.agir(async () => {
      await this.administration.suspendre(compte.id, motif);
      this.suspension.set(null);
      this.confirmation.set(`${compte.email} est suspendu.`);
    });
  }

  protected async reactiver(compte: CompteAdmin): Promise<void> {
    await this.agir(async () => {
      await this.administration.reactiver(compte.id);
      this.confirmation.set(`${compte.email} peut de nouveau se connecter.`);
    });
  }

  /**
   * Suppression définitive.
   *
   * LA CONFIRMATION EST EXIGÉE, et elle demande de retaper l'adresse :
   * un simple « êtes-vous sûr ? » se clique sans lire, alors que
   * recopier une adresse oblige à regarder de quel compte il s'agit.
   */
  protected readonly suppression = signal<number | null>(null);
  protected readonly confirmationSuppression = signal('');

  protected ouvrirSuppression(compte: CompteAdmin): void {
    this.erreur.set(null);
    this.confirmation.set(null);
    this.suppression.set(compte.id);
    this.confirmationSuppression.set('');
  }

  protected async supprimer(compte: CompteAdmin): Promise<void> {
    if (this.confirmationSuppression().trim() !== compte.email) {
      this.erreur.set(
        "Recopiez l'adresse exacte du compte pour confirmer la suppression.",
      );
      return;
    }
    await this.agir(async () => {
      await this.administration.supprimer(compte.id);
      this.suppression.set(null);
      this.confirmation.set(
        `${compte.email} et ses données personnelles ont été supprimés.`,
      );
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

  // --- Catalogue -------------------------------------------------------

  /**
   * Forfait en cours d'édition, ou `'nouveau'` pour une création.
   *
   * UN SEUL À LA FOIS. Ouvrir plusieurs formulaires laisserait croire
   * qu'ils s'enregistrent ensemble, alors que chaque forfait part dans
   * sa propre requête et peut être refusé séparément.
   */
  protected readonly edition = signal<string | null>(null);
  protected readonly brouillon = signal<ForfaitEcriture & { code: string }>({
    code: '',
    libelle: '',
    prix_fcfa: 0,
    credits: 0,
    argumentaire: '',
    atouts: [],
    essai: false,
    actif: true,
    ordre: 100,
  });
  /** Les atouts se saisissent une ligne par argument. */
  protected readonly atoutsTexte = signal('');

  protected ouvrirEdition(f: ForfaitAdmin): void {
    this.erreur.set(null);
    this.confirmation.set(null);
    this.edition.set(f.code);
    this.brouillon.set({
      code: f.code,
      libelle: f.libelle,
      prix_fcfa: f.prix_fcfa,
      credits: f.credits,
      argumentaire: f.argumentaire,
      atouts: f.atouts,
      essai: f.essai,
      actif: f.actif,
      ordre: f.ordre,
    });
    this.atoutsTexte.set(f.atouts.join('\n'));
  }

  protected ouvrirCreation(): void {
    this.erreur.set(null);
    this.confirmation.set(null);
    this.edition.set('nouveau');
    this.brouillon.set({
      code: '',
      libelle: '',
      prix_fcfa: 0,
      credits: 0,
      argumentaire: '',
      atouts: [],
      essai: false,
      actif: true,
      ordre: 100,
    });
    this.atoutsTexte.set('');
  }

  protected fermerEdition(): void {
    this.edition.set(null);
  }

  protected champ(cle: keyof (ForfaitEcriture & { code: string }), valeur: unknown): void {
    this.brouillon.update((b) => ({ ...b, [cle]: valeur }));
  }

  /**
   * Ce que coûterait le forfait en cours de saisie.
   *
   * AFFICHÉ PENDANT LA SAISIE, pas seulement au refus : voir la marge
   * chuter en tapant vaut mieux que se faire refuser après coup. Le
   * serveur reste seul juge — ce calcul ne fait qu'annoncer sa réponse.
   */
  protected margeBrouillon(): number | null {
    const b = this.brouillon();
    if (b.prix_fcfa <= 0) return null;
    const cout = b.credits * this.coutQuestion();
    return (b.prix_fcfa - cout) / b.prix_fcfa;
  }

  /**
   * Coût d'une question, déduit d'un forfait payant existant.
   *
   * Le serveur ne l'expose pas directement ; on le retrouve à partir
   * d'un forfait dont on connaît prix, crédits et marge. À défaut, on
   * n'affiche pas d'estimation plutôt que d'en inventer une.
   */
  protected coutQuestion(): number {
    const reference = this.forfaitsAdmin().find(
      (f) => f.credits > 0 && f.cout_variable_fcfa > 0,
    );
    return reference ? reference.cout_variable_fcfa / reference.credits : 0;
  }

  protected async enregistrerForfait(): Promise<void> {
    const b = this.brouillon();
    const atouts = this.atoutsTexte()
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    const corps: ForfaitEcriture = {
      libelle: b.libelle.trim(),
      prix_fcfa: Number(b.prix_fcfa) || 0,
      credits: Number(b.credits) || 0,
      argumentaire: b.argumentaire.trim(),
      atouts,
      essai: b.essai,
      actif: b.actif,
      ordre: Number(b.ordre) || 100,
    };

    await this.agir(async () => {
      if (this.edition() === 'nouveau') {
        await this.administration.creerForfait(b.code.trim(), corps);
        this.confirmation.set(`Forfait « ${corps.libelle} » créé.`);
      } else {
        await this.administration.modifierForfait(b.code, corps);
        this.confirmation.set(`Forfait « ${corps.libelle} » mis à jour.`);
      }
      this.edition.set(null);
      this.forfaitsAdmin.set(await this.administration.forfaits());
    });
  }

  // --- Signalements ----------------------------------------------------

  protected readonly corrections = signal<Record<number, string>>({});

  protected correction(id: number): string {
    return this.corrections()[id] ?? '';
  }

  protected poserCorrection(id: number, valeur: string): void {
    this.corrections.update((c) => ({ ...c, [id]: valeur }));
  }

  protected async clore(
    signalement: Signalement,
    statut: 'traite' | 'ecarte',
  ): Promise<void> {
    const correction = this.correction(signalement.id).trim();
    if (correction.length < 3) {
      this.erreur.set(
        'Dites ce qui a été constaté ou corrigé : sans cela, le registre ne prouve rien le jour où il faudrait s’en servir.',
      );
      return;
    }
    await this.agir(async () => {
      await this.administration.traiterSignalement(
        signalement.id,
        statut,
        correction,
      );
      this.confirmation.set(
        statut === 'traite'
          ? 'Signalement clos : correction consignée.'
          : 'Signalement écarté, motif consigné.',
      );
      this.signalements.set(await this.administration.signalements());
    });
  }

}
