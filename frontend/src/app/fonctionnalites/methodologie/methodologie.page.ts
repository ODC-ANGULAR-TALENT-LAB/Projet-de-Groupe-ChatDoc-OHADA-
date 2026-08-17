import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LigneProvenance } from '../../core/models';
import { CorpusService } from '../../core/services/corpus.service';

/**
 * Méthodologie, sources et limites.
 *
 * CETTE PAGE EST UNE PIÈCE DE PROTECTION, pas une page « à propos ». Le
 * cahier des charges (§2 ter) la décrit ainsi : « Cette table est aussi
 * la protection du projet : toute réponse contestée peut être remontée à
 * sa source exacte. »
 *
 * Elle est publique et consultable sans compte — une transparence qu'il
 * faudrait un compte pour lire n'en serait pas une.
 */
@Component({
  selector: 'app-methodologie',
  standalone: true,
  imports: [RouterLink],
  template: `
    <section class="page">
      <header>
        <h1>Méthodologie &amp; sources</h1>
        <p class="intro">
          Comment les réponses sont produites, d'où viennent les textes, et
          ce que cet outil ne fait pas.
        </p>
      </header>

      <section class="bloc">
        <h2>Comment une réponse est produite</h2>
        <ol class="etapes">
          <li>
            <strong>Recherche</strong> — la question est confrontée au corpus,
            par le sens et par les mots. Aucun texte extérieur n'est consulté.
          </li>
          <li>
            <strong>Seuil</strong> — si rien d'assez proche ne remonte,
            l'assistant refuse <em>sans même interroger le modèle</em>.
          </li>
          <li>
            <strong>Rédaction</strong> — le modèle ne reçoit que les articles
            retrouvés, avec la consigne de n'affirmer que ce qu'ils portent.
          </li>
          <li>
            <strong>Validation</strong> — chaque article cité est vérifié
            comme ayant réellement figuré dans les extraits fournis. Une
            citation qui n'y était pas fait rejeter la réponse entière.
          </li>
        </ol>
        <p class="aide">
          C'est cette dernière étape qui rend la promesse « aucune réponse
          inventée » <strong>vérifiable</strong> plutôt que déclarée.
        </p>
      </section>

      <section class="bloc">
        <h2>Provenance du corpus</h2>
        <p class="aide">
          Chaque texte porte sa source officielle, l'empreinte SHA-256 du
          fichier ingéré, sa version consolidée et le nom de la personne qui
          en répond. Toute réponse contestée peut ainsi être remontée à sa
          source exacte.
        </p>

        @if (lignes() === null) {
          <p class="vide">Chargement…</p>
        } @else if (!lignes()!.length) {
          <p class="vide">Aucun texte n'est encore publié.</p>
        } @else {
          <div class="tableau">
            <table>
              <caption class="invisible">Table de provenance du corpus</caption>
              <thead>
                <tr>
                  <th scope="col">Texte</th>
                  <th scope="col">Version</th>
                  <th scope="col">Consolidé au</th>
                  <th scope="col">Articles</th>
                  <th scope="col">Validé par</th>
                  <th scope="col">Source</th>
                </tr>
              </thead>
              <tbody>
                @for (ligne of lignes(); track ligne.id) {
                  <tr>
                    <th scope="row">
                      <span class="sigle">{{ ligne.sigle }}</span>
                      <span class="titre">{{ ligne.titre }}</span>
                    </th>
                    <td>{{ ligne.version }}</td>
                    <td class="nombre">{{ ligne.date_consolidation }}</td>
                    <td class="nombre">
                      {{ ligne.articles }}
                      <!-- Un article non vectorisé ne remonte que sur les
                           mots, pas sur le sens : le dire plutôt que de
                           laisser la recherche se dégrader en silence. -->
                      @if (ligne.vectorises < ligne.articles) {
                        <span class="alerte" [title]="ligne.vectorises + ' indexés'">
                          {{ ligne.vectorises }} indexés
                        </span>
                      }
                    </td>
                    <td>{{ ligne.valide_par || '—' }}</td>
                    <td>
                      @if (ligne.source_url) {
                        <a [href]="ligne.source_url" target="_blank" rel="noopener">
                          document officiel
                        </a>
                      } @else {
                        —
                      }
                      @if (ligne.source_sha256) {
                        <span class="sha">{{ ligne.source_sha256.slice(0, 12) }}…</span>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }

        <p class="aide">
          <a routerLink="/journal">Voir le journal des mises à jour →</a>
        </p>
      </section>

      <section class="bloc limites">
        <h2>Limites de l'outil</h2>
        <p>
          ChatDocs OHADA est une <strong>aide à la recherche documentaire</strong>.
          Il ne constitue ni une consultation juridique, ni un conseil fiscal,
          ni un acte relevant d'une profession réglementée.
        </p>
        <p>
          L'outil répond bien aux questions factuelles — un délai, un taux, une
          mention obligatoire. Il est <strong>moins fiable</strong> sur le
          raisonnement combinant plusieurs textes, sur l'interprétation et sur
          les cas d'espèce : dans ces situations, il refuse plutôt que d'avancer.
        </p>
        <p>
          Seul le <strong>texte brut officiel</strong> est ingéré, jamais le
          contenu éditorial d'un tiers. L'extrait est affiché précisément pour
          que vous exerciez votre propre contrôle professionnel.
        </p>
      </section>
    </section>
  `,
  styleUrl: './methodologie.page.scss',
})
export class MethodologiePage {
  private readonly corpus = inject(CorpusService);

  protected readonly lignes = signal<LigneProvenance[] | null>(null);

  constructor() {
    void this.charger();
  }

  private async charger(): Promise<void> {
    try {
      this.lignes.set(await this.corpus.provenance());
    } catch {
      this.lignes.set([]);
    }
  }
}
