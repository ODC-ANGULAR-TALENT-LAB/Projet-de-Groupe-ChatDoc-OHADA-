import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ConformiteService, ModeleConformite, RapportConformite } from '../../core/services/conformite.service';
import { AuthService } from '../../core/services/auth.service';
import { IconeComponent } from '../../partage/composants/icone.component';

/**
 * Analyse de conformité d'un document déposé.
 *
 * LE RAPPORT NE DONNE AUCUNE NOTE GLOBALE. Un « 85 % conforme » se
 * retient, se cite, et laisse croire à une garantie que le produit
 * refuse explicitement de donner : le cahier des charges range la
 * garantie de conformité hors périmètre (§3), obligation de moyens et
 * jamais de résultat. On rend des comptes, pas une note.
 *
 * Chaque point porte l'article qui le fonde. Un écart sans base légale
 * n'est qu'une opinion ; avec l'article, c'est une pièce de travail.
 */
@Component({
  selector: 'app-conformite',
  standalone: true,
  imports: [FormsModule, RouterLink, IconeComponent],
  template: `
    <section class="page">
      <header>
        <h1>Analyse de conformité</h1>
        <p class="intro">
          Déposez un document : l'outil vérifie, point par point, les mentions
          que la loi impose — et vous dit sous quel article.
        </p>
      </header>

      @if (!auth.connecte()) {
        <p class="vide">
          Cette analyse demande un compte.
          <a routerLink="/connexion">Se connecter</a>
        </p>
      } @else {
        <section class="bloc">
          <form class="depot" (ngSubmit)="lancer()">
            <label for="modele">Type de document</label>
            <select id="modele" name="modele" [(ngModel)]="modele">
              @for (m of modeles(); track m.cle) {
                <option [value]="m.cle">
                  {{ m.libelle }} — {{ m.sigle }} article {{ m.numero }}
                </option>
              }
            </select>

            <label for="fichier">Document (PDF ou texte)</label>
            <input id="fichier" type="file" accept="application/pdf,text/plain"
                   (change)="choisir($event)" />

            <p class="aide">
              Le fichier est lu puis <strong>oublié</strong> : il n'est écrit
              nulle part sur le serveur, et le rapport n'est pas conservé.
            </p>

            @if (erreur()) {
              <p class="erreur" role="alert">{{ erreur() }}</p>
            }

            <button type="submit" class="principal" [disabled]="occupe()">
              {{ occupe() ? 'Analyse en cours…' : 'Analyser le document' }}
            </button>
          </form>
        </section>

        @if (rapport(); as r) {
          <section class="bloc">
            <h2>Rapport — {{ r.modele }}</h2>

            <div class="compteurs">
              <span class="pastille conforme">{{ r.compte['conforme'] || 0 }} conforme(s)</span>
              <span class="pastille ecart">{{ r.compte['ecart'] || 0 }} écart(s)</span>
              <span class="pastille a_verifier">{{ r.compte['a_verifier'] || 0 }} à vérifier</span>
            </div>

            <p class="fondement">
              <app-icone nom="balance" />
              Grille tirée de
              <a [routerLink]="['/article', r.article_id]">
                l'article {{ r.numero }} de l'{{ r.sigle }}
              </a>
              — corpus {{ r.version_corpus }}
            </p>

            <ol class="points">
              @for (point of r.points; track point.repere) {
                <li [class]="point.statut">
                  <div class="entete">
                    <span class="repere">{{ point.repere }}</span>
                    <span class="libelle">{{ point.libelle }}</span>
                    <span class="pastille" [class]="point.statut">
                      {{ libelle(point.statut) }}
                    </span>
                  </div>
                  <p class="constat">{{ point.constat }}</p>
                </li>
              }
            </ol>

            <p class="avertissement">
              Ce rapport constate ce qui a été vu dans le document. Il ne
              garantit pas la conformité juridique de l'acte, ni sa validité :
              faites-le valider par un professionnel.
            </p>
          </section>
        }
      }
    </section>
  `,
  styleUrl: './conformite.page.scss',
})
export class ConformitePage {
  protected readonly auth = inject(AuthService);
  private readonly service = inject(ConformiteService);

  protected readonly modeles = signal<ModeleConformite[]>([]);
  protected readonly rapport = signal<RapportConformite | null>(null);
  protected readonly erreur = signal<string | null>(null);
  protected readonly occupe = signal(false);

  protected modele = 'statuts_societe';
  private fichier: File | null = null;

  constructor() {
    void this.charger();
  }

  private async charger(): Promise<void> {
    try {
      this.modeles.set(await this.service.modeles());
    } catch {
      this.modeles.set([]);
    }
  }

  protected libelle(statut: string): string {
    return { conforme: 'conforme', ecart: 'écart', a_verifier: 'à vérifier' }[
      statut
    ] ?? statut;
  }

  protected choisir(evenement: Event): void {
    this.fichier = (evenement.target as HTMLInputElement).files?.[0] ?? null;
  }

  protected async lancer(): Promise<void> {
    this.erreur.set(null);
    if (!this.fichier) {
      this.erreur.set('Choisissez un document à analyser.');
      return;
    }

    this.occupe.set(true);
    try {
      this.rapport.set(await this.service.analyser(this.fichier, this.modele));
    } catch (erreur) {
      this.rapport.set(null);
      this.erreur.set(this.service.message(erreur));
    } finally {
      this.occupe.set(false);
    }
  }
}
