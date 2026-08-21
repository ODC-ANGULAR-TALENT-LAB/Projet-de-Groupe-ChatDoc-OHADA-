import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, input } from '@angular/core';

/**
 * Rendu Markdown des réponses de l'assistant.
 *
 * POURQUOI PAS UNE BIBLIOTHÈQUE. `marked` ou `markdown-it` pèsent une
 * cinquantaine de kilo-octets pour un sous-ensemble dont nous n'utilisons
 * rien : ni tableaux, ni images, ni HTML brut, ni notes de bas de page.
 * L'application doit rester légère et consultable hors ligne, et un
 * moteur générique ouvrirait une surface d'injection HTML là où nous
 * affichons du texte produit par un modèle.
 *
 * POURQUOI PAS innerHTML. Le texte rendu ici vient d'un LLM. Même avec
 * un prompt strict, le traiter comme du HTML de confiance serait une
 * faute : on construit donc un ARBRE de nœuds typés, qu'Angular rend
 * comme du texte. Aucune chaîne n'est jamais interprétée comme du
 * balisage — l'injection est impossible par construction, pas par
 * échappement.
 *
 * Sous-ensemble volontairement pauvre :
 *   **gras**  *italique*  `code`
 *   - listes à puces        1. listes numérotées
 *   paragraphes séparés par une ligne vide
 */

/** Un fragment de ligne : du texte, avec ou sans emphase. */
interface Fragment {
  texte: string;
  gras?: boolean;
  italique?: boolean;
  code?: boolean;
}

interface Bloc {
  type: 'paragraphe' | 'liste' | 'liste-numerotee' | 'titre';
  lignes: Fragment[][];
}

// Emphases reconnues, dans l'ordre où on les cherche. `**` avant `*`,
// sinon le gras serait lu comme deux italiques vides.
const MARQUEURS: { motif: RegExp; cle: keyof Fragment }[] = [
  { motif: /\*\*([^*]+)\*\*/, cle: 'gras' },
  { motif: /\*([^*]+)\*/, cle: 'italique' },
  { motif: /`([^`]+)`/, cle: 'code' },
];

const RE_PUCE = /^\s*[-–—*]\s+(.*)$/;
const RE_NUMERO = /^\s*\d+[.)]\s+(.*)$/;

// TITRES DE SECTION. Sans cette reconnaissance, une reponse structuree
// afficherait « ## Ce que dit le texte » avec ses dieses en clair : le
// prompt demande des sections, le rendu doit savoir les dessiner.
//
// Un seul niveau visuel, quel que soit le nombre de dieses. Une reponse
// tient dans un ecran ; y hierarchiser trois rangs de titres n'aiderait
// personne et multiplierait les tailles de police a l'ecran.
const RE_TITRE = /^\s*#{1,4}\s+(.*?)\s*#*$/;

/** Découpe une ligne en fragments, emphases comprises. */
export function fragmenter(ligne: string): Fragment[] {
  for (const { motif, cle } of MARQUEURS) {
    const trouve = motif.exec(ligne);
    if (!trouve) continue;

    const avant = ligne.slice(0, trouve.index);
    const apres = ligne.slice(trouve.index + trouve[0].length);
    return [
      ...(avant ? fragmenter(avant) : []),
      { texte: trouve[1], [cle]: true },
      ...(apres ? fragmenter(apres) : []),
    ];
  }
  return ligne ? [{ texte: ligne }] : [];
}

/** Découpe un texte en blocs : paragraphes et listes. */
export function analyser(texte: string): Bloc[] {
  const blocs: Bloc[] = [];
  let courant: Bloc | null = null;

  const clore = () => {
    if (courant) blocs.push(courant);
    courant = null;
  };

  for (const ligne of (texte ?? '').split('\n')) {
    const nue = ligne.trim();
    if (!nue) {
      clore();
      continue;
    }

    // Le titre est cherché EN PREMIER : « # 1. Champ d'application »
    // satisfait aussi RE_NUMERO une fois le dièse retiré, et l'ordre
    // inverse en ferait une liste numérotée à un seul élément.
    const titre = RE_TITRE.exec(ligne);
    const puce = titre ? null : RE_PUCE.exec(ligne);
    const numero = titre ? null : RE_NUMERO.exec(ligne);
    const type: Bloc['type'] = titre
      ? 'titre'
      : puce
        ? 'liste'
        : numero
          ? 'liste-numerotee'
          : 'paragraphe';

    // Un titre ne se fond jamais dans le bloc précédent, même avec un
    // autre titre : deux sections successives sont deux titres.
    if (!courant || courant.type !== type || type === 'titre') {
      clore();
      courant = { type, lignes: [] };
    }

    const contenu = titre?.[1] ?? puce?.[1] ?? numero?.[1] ?? nue;
    if (type === 'paragraphe' && courant.lignes.length) {
      // Une phrase coupée sur plusieurs lignes reste un seul paragraphe.
      courant.lignes[0] = [...courant.lignes[0], { texte: ' ' + contenu }];
    } else {
      courant.lignes.push(fragmenter(contenu));
    }
  }
  clore();

  return blocs;
}

@Component({
  selector: 'app-markdown',
  standalone: true,
  imports: [NgTemplateOutlet],
  template: `
    @for (bloc of blocs(); track $index) {
      @switch (bloc.type) {
        @case ('liste') {
          <ul>
            @for (ligne of bloc.lignes; track $index) {
              <li>
                @for (f of ligne; track $index) {
                  <ng-container
                    [ngTemplateOutlet]="frag"
                    [ngTemplateOutletContext]="{ $implicit: f }"
                  />
                }
              </li>
            }
          </ul>
        }
        @case ('liste-numerotee') {
          <ol>
            @for (ligne of bloc.lignes; track $index) {
              <li>
                @for (f of ligne; track $index) {
                  <ng-container
                    [ngTemplateOutlet]="frag"
                    [ngTemplateOutletContext]="{ $implicit: f }"
                  />
                }
              </li>
            }
          </ol>
        }
        @case ('titre') {
          @for (ligne of bloc.lignes; track $index) {
            <h3>
              @for (f of ligne; track $index) {
                <ng-container
                  [ngTemplateOutlet]="frag"
                  [ngTemplateOutletContext]="{ $implicit: f }"
                />
              }
            </h3>
          }
        }
        @default {
          @for (ligne of bloc.lignes; track $index) {
            <p>
              @for (f of ligne; track $index) {
                <ng-container
                  [ngTemplateOutlet]="frag"
                  [ngTemplateOutletContext]="{ $implicit: f }"
                />
              }
            </p>
          }
        }
      }
    }

    <!-- Chaque fragment est un nœud de TEXTE : rien n'est interprété
         comme du balisage. -->
    <ng-template #frag let-f>
      @if (f.gras) {
        <strong>{{ f.texte }}</strong>
      } @else if (f.italique) {
        <em>{{ f.texte }}</em>
      } @else if (f.code) {
        <code>{{ f.texte }}</code>
      } @else {
        {{ f.texte }}
      }
    </ng-template>
  `,
  styles: `
    :host {
      display: block;
    }

    p {
      margin: 0 0 0.85em;
      line-height: 1.65;
    }

    p:last-child,
    ul:last-child,
    ol:last-child,
    h3:last-child {
      margin-bottom: 0;
    }

    /* Titre de section. Il se distingue par la graisse et la famille,
       non par la taille : une réponse comporte trois ou quatre
       sections, et des titres nettement plus gros que le texte
       hacheraient la lecture au lieu de la guider.

       La marge haute est plus large que la basse : elle rattache
       visuellement le titre à ce qui le suit plutôt qu'à ce qui le
       précède. */
    h3 {
      margin: 1.4em 0 0.5em;
      font-family: var(--police-titre, inherit);
      font-size: 1em;
      font-weight: 600;
      color: var(--bleu-nuit);
      line-height: 1.4;
    }

    h3:first-child {
      margin-top: 0;
    }

    ul,
    ol {
      margin: 0 0 0.85em;
      padding-left: 1.3em;
    }

    li {
      margin-bottom: 0.3em;
      line-height: 1.6;
    }

    code {
      font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
      font-size: 0.9em;
      background: var(--surface-basse);
      padding: 0.1em 0.35em;
      border-radius: 3px;
    }
  `,
})
export class MarkdownComponent {
  readonly texte = input.required<string>();

  protected readonly blocs = computed(() => analyser(this.texte()));
}
