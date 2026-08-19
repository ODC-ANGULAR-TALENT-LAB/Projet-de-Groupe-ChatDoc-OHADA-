import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ErreurApi } from '../../core/services/api.service';
import {
  AdminService,
  Depot,
  DepotDetail,
  EntreeDiff,
  StatutDiff,
} from '../../core/services/admin.service';
import { AuthService } from '../../core/services/auth.service';

/**
 * Back-office d'ingestion du corpus.
 *
 * Quatre temps, délibérément : on dépose, on compare au corpus en
 * vigueur, on relit ce qui a bougé, puis on valide.
 * Téléverser alimente le corpus interrogé — jamais les poids du
 * modèle. Il n'y a aucun entraînement ici.
 */
@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <section class="page">
      @if (!estAdmin()) {
        <h1>Espace juriste</h1>
        <p class="vide">
          Cet espace est réservé aux juristes responsables du corpus.
          <a routerLink="/connexion">Se connecter</a>
        </p>
      } @else {
        <header>
          <h1>Espace juriste — tenue du corpus</h1>
          <p class="intro">
            Téléverser un texte alimente le <strong>corpus interrogé</strong>,
            jamais les paramètres du modèle. Un document déposé n'est pas
            consultable&nbsp;: il faut le relire, puis le valider.
          </p>
        </header>

        <!-- 1. DÉPÔT -->
        <section class="bloc">
          <h2>1. Déposer un texte officiel</h2>
          <p class="aide">
            La provenance est obligatoire. Sans URL officielle, version et date
            de consolidation, une réponse contestée ne peut pas être remontée à
            sa source — et c'est cette traçabilité qui protège le projet.
          </p>

          <form class="formulaire" (ngSubmit)="deposer()">
            <label for="fichier">Fichier PDF officiel</label>
            <input id="fichier" type="file" accept="application/pdf"
                   (change)="choisirFichier($event)" />

            <label for="url">URL officielle exacte</label>
            <input id="url" name="url" type="url" [(ngModel)]="p.source_url"
                   placeholder="https://www.ohada.org/…" required />

            <div class="ligne">
              <div>
                <label for="sigle">Sigle</label>
                <input id="sigle" name="sigle" [(ngModel)]="p.sigle"
                       placeholder="AUSCGIE" maxlength="20" required />
              </div>
              <div>
                <label for="type">Nature</label>
                <select id="type" name="type" [(ngModel)]="p.type">
                  <option value="acte_uniforme">Acte uniforme</option>
                  <option value="code">Code</option>
                </select>
              </div>
            </div>

            <label for="titre">Intitulé complet</label>
            <input id="titre" name="titre" [(ngModel)]="p.titre"
                   placeholder="Acte uniforme relatif au droit des sociétés…"
                   required />

            <div class="ligne">
              <div>
                <label for="version">Version</label>
                <input id="version" name="version" [(ngModel)]="p.version"
                       placeholder="révision 2014" required />
              </div>
              <div>
                <label for="date">Date de consolidation</label>
                <input id="date" name="date" type="date"
                       [(ngModel)]="p.date_consolidation" required />
              </div>
              <div>
                <label for="page">Page de départ</label>
                <input id="page" name="page" type="number" min="1"
                       [(ngModel)]="p.page_debut" />
              </div>
            </div>
            <p class="aide">
              La page de départ écarte le sommaire, qui produirait sinon autant
              de faux articles que d'entrées.
            </p>

            @if (erreur()) {
              <p class="erreur" role="alert">{{ erreur() }}</p>
            }

            <button type="submit" class="principal" [disabled]="occupe()">
              {{ occupe() ? 'Analyse en cours…' : 'Déposer et analyser' }}
            </button>
          </form>
        </section>

        <!-- 2. RELECTURE -->
        @if (detail(); as d) {
          <section class="bloc">
            <h2>2. Situer et relire — dépôt {{ d.id }}</h2>

            <dl class="resume">
              <div><dt>Articles</dt><dd>{{ d.nb_articles }}</dd></div>
              <div><dt>Pages</dt><dd>{{ d.nb_pages }}</dd></div>
              <div>
                <dt>Problèmes bloquants</dt>
                <dd [class.mauvais]="d.nb_bloquants > 0">{{ d.nb_bloquants }}</dd>
              </div>
              <div><dt>Empreinte</dt><dd class="sha">{{ d.sha256.slice(0, 16) }}…</dd></div>
            </dl>

            @if (d.problemes.length) {
              <ul class="problemes">
                @for (probleme of d.problemes; track $index) {
                  <li [class.bloquant]="probleme.niveau === 'bloquant'">
                    <strong>{{ probleme.niveau }}</strong> — {{ probleme.message }}
                  </li>
                }
              </ul>
            }

            <!-- 2 bis. SITUER LE DÉPÔT DANS LE CORPUS -->
            @if (!d.analyse.length) {
              <p class="aide">
                Avant de relire, situe ce dépôt par rapport au corpus déjà en
                vigueur : tu ne reliras que les articles qui ont réellement
                bougé, pas les {{ d.nb_articles }}.
              </p>
              <button type="button" class="principal" [disabled]="occupe()"
                      (click)="analyser(d.id)">
                Comparer au corpus en vigueur
              </button>
            } @else {
              <div class="compteurs">
                @for (paire of compte(d); track paire[0]) {
                  <span class="pastille" [class]="paire[0]">
                    {{ paire[1] }} {{ libelle(paire[0]) }}
                  </span>
                }
              </div>

              @if (!aRelire(d).length) {
                <p class="aide">
                  Aucun article n'a changé par rapport au corpus en vigueur.
                </p>
              } @else {
                <p class="aide">
                  <strong>{{ aRelire(d).length }} article(s) à relire</strong> sur
                  {{ d.nb_articles }}. Compare chacun au PDF officiel, puis
                  coche-le. La validation engage ta signature : c'est ton nom
                  qui figurera dans la table de provenance.
                </p>

                <div class="diff">
                  @for (entree of aRelire(d); track entree.numero) {
                    <article [class]="entree.statut">
                      <header>
                        <label>
                          <input type="checkbox"
                                 [checked]="estRelu(d, entree.numero)"
                                 [disabled]="d.statut !== 'en_attente'"
                                 (change)="basculerRelu(d, entree.numero)" />
                          <span class="numero">Article {{ entree.numero }}</span>
                        </label>
                        <span class="pastille" [class]="entree.statut">
                          {{ libelle(entree.statut) }}
                        </span>
                      </header>

                      @if (entree.resume) {
                        <p class="resume">
                          <span class="etiquette">Résumé automatique</span>
                          {{ entree.resume }}
                        </p>
                      }

                      <div class="cote-a-cote">
                        @if (entree.ancien) {
                          <div class="ancien">
                            <h4>Version en vigueur</h4>
                            <p>{{ entree.ancien }}</p>
                          </div>
                        }
                        @if (entree.nouveau) {
                          <div class="nouveau">
                            <h4>Version déposée</h4>
                            <p>{{ entree.nouveau }}</p>
                          </div>
                        }
                      </div>
                    </article>
                  }
                </div>
              }
            }

            <details class="tout-voir">
              <summary>Voir le découpage complet ({{ d.nb_articles }} articles)</summary>
              <div class="apercu">
                @for (article of d.articles.slice(0, apercu()); track $index) {
                  <article>
                    <span class="numero">Article {{ article.numero }}</span>
                    <span class="chemin">{{ article.chemin || '(aucun chemin)' }}</span>
                    <p>{{ article.contenu }}</p>
                  </article>
                }
              </div>
              @if (d.articles.length > apercu()) {
                <button type="button" class="lien" (click)="voirPlus()">
                  Voir {{ pas }} articles de plus
                  ({{ apercu() }} / {{ d.articles.length }})
                </button>
              }
            </details>

            @if (d.statut === 'en_attente') {
              <div class="decision">
                <button type="button" class="principal"
                        [disabled]="!validable(d) || occupe()"
                        (click)="valider(d.id)">
                  Valider et publier dans le corpus
                </button>
                <button type="button" class="secondaire" [disabled]="occupe()"
                        (click)="rejeter(d.id)">
                  Rejeter
                </button>
              </div>
              @if (d.nb_bloquants > 0) {
                <p class="aide">
                  La validation est bloquée tant que des problèmes subsistent.
                  Un corpus mal découpé contamine toutes les réponses qui
                  s'appuieront dessus.
                </p>
              } @else if (restantARelire(d) > 0) {
                <p class="aide">
                  {{ restantARelire(d) }} article(s) modifié(s) restent à relire.
                </p>
              }
            } @else {
              <p class="statut">Statut : {{ d.statut }}</p>
              @if (d.texte_id) {
                <button type="button" class="secondaire" [disabled]="occupe()"
                        (click)="vectoriser(d.texte_id!)">
                  Calculer les embeddings manquants
                </button>
                @if (messageVectorisation(); as message) {
                  <p class="aide">{{ message }}</p>
                }
              }
            }
          </section>
        }

        <!-- 3. DÉPÔTS -->
        <section class="bloc">
          <h2>Dépôts</h2>
          @if (!admin.depots()?.length) {
            <p class="vide">Aucun dépôt pour l'instant.</p>
          } @else {
            <ul class="liste">
              @for (depot of admin.depots(); track depot.id) {
                <li>
                  <button type="button" class="ligne-depot"
                          (click)="ouvrir(depot)">
                    <span class="badge" [class]="depot.statut">{{ depot.statut }}</span>
                    <span class="nom">{{ depot.sigle }} — {{ depot.nom_fichier }}</span>
                    <span class="chiffres">
                      {{ depot.nb_articles }} art.
                      @if (depot.nb_bloquants) {
                        · <span class="mauvais">{{ depot.nb_bloquants }} bloq.</span>
                      }
                    </span>
                  </button>
                </li>
              }
            </ul>
          }
        </section>

        <!-- 4. ÉTAT DU CORPUS -->
        <section class="bloc">
          <h2>État du corpus</h2>
          @if (!admin.corpus()?.length) {
            <p class="vide">Le corpus est vide.</p>
          } @else {
            <table>
              <thead>
                <tr><th>Sigle</th><th>Version</th><th>Articles</th>
                    <th>Vectorisés</th><th>Validé par</th></tr>
              </thead>
              <tbody>
                @for (texte of admin.corpus(); track texte.id) {
                  <tr [class.incomplet]="!texte.pret">
                    <td>{{ texte.sigle }}</td>
                    <td>{{ texte.version }}</td>
                    <td>{{ texte.articles }}</td>
                    <td>{{ texte.vectorises }}</td>
                    <td class="valideur">{{ texte.valide_par }}</td>
                  </tr>
                }
              </tbody>
            </table>
            @if (aVectoriser()) {
              <p class="aide">
                Des articles ne sont pas encore vectorisés. Tant qu'ils ne le
                sont pas, ils ne remontent que par la recherche lexicale : la
                moitié vectorielle reste muette, sans que rien ne le signale
                côté utilisateur. Lance&nbsp;:
                <code>python ingestion/4_vectoriser.py --creer-index</code>
              </p>
            }
          }
        </section>
      }
    </section>
  `,
  styleUrl: './admin.page.scss',
})
export class AdminPage {
  protected readonly admin = inject(AdminService);
  private readonly auth = inject(AuthService);

  protected readonly pas = 10;
  protected readonly detail = signal<DepotDetail | null>(null);
  protected readonly apercu = signal(5);
  protected readonly erreur = signal<string | null>(null);
  protected readonly occupe = signal(false);
  protected readonly messageVectorisation = signal<string | null>(null);

  protected p = {
    source_url: '',
    sigle: '',
    titre: '',
    version: '',
    date_consolidation: '',
    type: 'acte_uniforme',
    page_debut: 1,
  };

  private fichier: File | null = null;

  constructor() {
    void this.charger();
  }

  /** Juriste ou administrateur : les deux tiennent le corpus. */
  protected estAdmin(): boolean {
    const role = this.auth.quota()?.role;
    return role === 'juriste' || role === 'admin';
  }

  // --- Lecture du diff --------------------------------------------

  private static readonly LIBELLES: Record<StatutDiff, string> = {
    ajoute: 'ajouté',
    modifie: 'modifié',
    abroge: 'abrogé',
    inchange: 'inchangé',
  };

  protected libelle(statut: StatutDiff): string {
    return AdminPage.LIBELLES[statut] ?? statut;
  }

  /** Compte par statut, dans un ordre stable pour l'affichage. */
  protected compte(depot: DepotDetail): [StatutDiff, number][] {
    const ordre: StatutDiff[] = ['modifie', 'ajoute', 'abroge', 'inchange'];
    return ordre
      .map((statut): [StatutDiff, number] => [
        statut,
        depot.analyse.filter((e) => e.statut === statut).length,
      ])
      .filter(([, n]) => n > 0);
  }

  /**
   * Les seules entrées qui demandent une décision.
   *
   * C'est tout l'apport du diff : un article inchangé n'a pas à être
   * relu. Les plus modifiés d'abord — le juriste doit voir en premier
   * ce qui a le plus bougé.
   */
  protected aRelire(depot: DepotDetail): EntreeDiff[] {
    return depot.analyse
      .filter((e) => e.statut !== 'inchange')
      .sort((a, b) => a.similarite - b.similarite);
  }

  protected estRelu(depot: DepotDetail, numero: string): boolean {
    return depot.articles_retenus.includes(numero);
  }

  protected restantARelire(depot: DepotDetail): number {
    return this.aRelire(depot).filter((e) => !this.estRelu(depot, e.numero)).length;
  }

  /** Aucun blocage, et tout ce qui a bougé a été relu. */
  protected validable(depot: DepotDetail): boolean {
    return depot.nb_bloquants === 0 && this.restantARelire(depot) === 0;
  }

  // --- Actions ------------------------------------------------------

  protected async analyser(id: number): Promise<void> {
    this.occupe.set(true);
    this.erreur.set(null);
    try {
      this.detail.set(await this.admin.analyser(id));
    } catch (erreur) {
      this.erreur.set(this.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  protected async basculerRelu(depot: DepotDetail, numero: string): Promise<void> {
    // La relecture est cumulative côté serveur : on n'envoie que ce qui
    // vient d'être coché. Décocher ne retire rien — on ne « dé-lit » pas
    // un article, et un aller-retour accidentel ne doit pas effacer une
    // relecture déjà faite.
    if (this.estRelu(depot, numero)) return;
    try {
      this.detail.set(await this.admin.marquerRelu(depot.id, [numero]));
    } catch (erreur) {
      this.erreur.set(this.message(erreur));
    }
  }

  protected async vectoriser(texteId: number): Promise<void> {
    this.occupe.set(true);
    try {
      const reponse = await this.admin.vectoriser(texteId);
      this.messageVectorisation.set(reponse.message);
      await this.admin.chargerCorpus();
    } catch (erreur) {
      this.erreur.set(this.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  protected aVectoriser(): boolean {
    return (this.admin.corpus() ?? []).some((t) => !t.pret);
  }

  protected choisirFichier(evenement: Event): void {
    const entree = evenement.target as HTMLInputElement;
    this.fichier = entree.files?.[0] ?? null;
  }

  protected voirPlus(): void {
    this.apercu.update((n) => n + this.pas);
  }

  protected async ouvrir(depot: Depot): Promise<void> {
    this.apercu.set(5);
    this.detail.set(await this.admin.detail(depot.id));
  }

  protected async deposer(): Promise<void> {
    this.erreur.set(null);
    if (!this.fichier) {
      this.erreur.set('Choisissez un fichier PDF.');
      return;
    }

    this.occupe.set(true);
    try {
      this.apercu.set(5);
      this.detail.set(await this.admin.deposer(this.fichier, this.p));
      await this.admin.chargerDepots();
    } catch (erreur) {
      this.erreur.set(this.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  protected async valider(id: number): Promise<void> {
    this.occupe.set(true);
    try {
      await this.admin.valider(id);
      this.detail.set(await this.admin.detail(id));
    } catch (erreur) {
      this.erreur.set(this.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  protected async rejeter(id: number): Promise<void> {
    this.occupe.set(true);
    try {
      await this.admin.rejeter(id);
      this.detail.set(await this.admin.detail(id));
    } catch (erreur) {
      this.erreur.set(this.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }

  /** Remonte le message du serveur : il explique précisément le refus. */
  private message(erreur: unknown): string {
    if (erreur instanceof ErreurApi) return erreur.message;
    const detail = (erreur as { error?: { detail?: unknown } })?.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return 'Champs manquants ou invalides : ' +
        detail.map((d: { loc?: string[] }) => d.loc?.at(-1)).join(', ');
    }
    return "Le dépôt a échoué.";
  }

  private async charger(): Promise<void> {
    await this.auth.rafraichirQuota();
    if (!this.estAdmin()) return;
    try {
      await this.admin.chargerDepots();
      await this.admin.chargerCorpus();
    } catch {
      this.erreur.set("Le back-office n'a pas pu être chargé.");
    }
  }
}
