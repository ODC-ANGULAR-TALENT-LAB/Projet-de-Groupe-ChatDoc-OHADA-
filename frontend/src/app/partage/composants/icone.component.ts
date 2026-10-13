import { Component, computed, input } from '@angular/core';

/**
 * Jeu d'icônes de l'application.
 *
 * POURQUOI PAS D'EMOJI. La navigation utilisait 💬 📚 🕘 👤 🗂️. Un emoji
 * n'est pas une icône : son dessin appartient au système, il change
 * d'une plateforme à l'autre, il ne prend ni la couleur ni l'épaisseur de
 * trait du reste de l'interface, et il jure avec une identité d'édition
 * juridique. C'est le défaut qui fait « prototype » au premier regard.
 *
 * POURQUOI PAS UNE BIBLIOTHÈQUE. L'application doit rester consultable
 * hors ligne (PWA, bibliothèque en cache). Une icône servie par un CDN
 * disparaît dès que le réseau tombe, et une dépendance npm d'icônes
 * embarquerait un millier de dessins pour la dizaine utilisée ici. Les
 * tracés vivent donc dans ce fichier.
 *
 * Tracés au style Lucide : grille 24, trait de 1,5 px, extrémités
 * arrondies. Une seule épaisseur pour tout le jeu — mélanger les
 * épaisseurs est ce qui trahit le plus vite un assemblage d'icônes
 * dépareillées.
 */

/** Tracés, indexés par nom. Grille 24×24. */
const TRACES: Record<string, string[]> = {
  // UNE ICÔNE, UN SENS. Plusieurs entrées empruntaient l'icône d'une
  // autre : « Assistant » celle du bouton « Nouvelle question »,
  // « Administration » et « Forfaits » celle du profil, « Mises à jour »
  // celle de l'historique, « Votre avis » le drapeau de signalement. Sur
  // téléphone, où l'on choisit au coup d'œil, deux entrées au même dessin
  // se confondent — et un drapeau pour « donner son avis » dit « signaler
  // un problème ». Les huit tracés qui suivent leur rendent un sens propre.
  assistant: [
    'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
    'M13 8H7',
    'M17 12H7',
  ],
  bouclier: [
    'M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z',
    'm9 12 2 2 4-4',
  ],
  calculatrice: [
    'M6 2h12a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z',
    'M8 6h8',
    'M16 14v4',
    'M16 10h.01',
    'M12 10h.01',
    'M8 10h.01',
    'M12 14h.01',
    'M8 14h.01',
    'M12 18h.01',
    'M8 18h.01',
  ],
  conformite: [
    'M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z',
    'M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2',
    'm9 14 2 2 4-4',
  ],
  forfait: [
    'M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z',
    'M2 10h20',
    'M6 15h4',
  ],
  methodologie: [
    'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z',
    'M12 16v-4',
    'M12 8h.01',
  ],
  journal: [
    'M10.27 21a2 2 0 0 0 3.46 0',
    'M3.26 15.33A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.67C19.41 13.96 18 12.5 18 8A6 6 0 0 0 6 8c0 4.5-1.41 5.96-2.74 7.33',
  ],
  avis: [
    'M11.53 2.3a.53.53 0 0 1 .95 0l2.31 4.68a2.12 2.12 0 0 0 1.6 1.16l5.16.76a.53.53 0 0 1 .3.9l-3.74 3.64a2.12 2.12 0 0 0-.61 1.88l.88 5.14a.53.53 0 0 1-.77.56l-4.62-2.43a2.12 2.12 0 0 0-1.97 0L6.4 21.01a.53.53 0 0 1-.77-.56l.88-5.14a2.12 2.12 0 0 0-.61-1.88L2.16 9.8a.53.53 0 0 1 .3-.91l5.16-.75a2.12 2.12 0 0 0 1.6-1.16z',
  ],
  'nouveau-chat': [
    'M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7',
    'M18.4 2.6a1.9 1.9 0 0 1 2.7 2.7L12.5 14l-3.6 1 1-3.6z',
  ],
  // Livre ouvert plutôt que la pile de tranches : à 20 px, la pile se
  // lit comme quatre barres sans signification.
  bibliotheque: [
    'M12 7v14',
    'M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z',
  ],
  historique: [
    'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8',
    'M3 3v5h5',
    'M12 7v5l4 2',
  ],
  compte: ['M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2', 'M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8'],
  corpus: [
    'M3 3h18v5H3z',
    'M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8',
    'M10 12h4',
  ],
  deconnexion: [
    'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4',
    'm16 17 5-5-5-5',
    'M21 12H9',
  ],
  envoyer: ['M22 2 11 13', 'M22 2 15 22l-4-9-9-4z'],
  // Balance de la justice : l'icône du bloc « Base légale ».
  balance: [
    'M12 3v18',
    'M7 21h10',
    'M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2',
    'm16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z',
    'm2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z',
  ],
  fleche: ['M5 12h14', 'm12 5 7 7-7 7'],
  copier: [
    'M9 9h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V11a2 2 0 0 1 2-2',
    'M5 15H4a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1',
  ],
  valide: ['M20 6 9 17l-5-5'],
  // Un signet, pas une etoile : une etoile note, un signet marque. Ici
  // l'utilisateur ne juge pas l'article, il le met de cote.
  favori: ['M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z'],
  // Une cloche pour la veille : l'alerte porte sur un texte qui a
  // bouge, pas sur une erreur.
  veille: [
    'M10.3 21a1.94 1.94 0 0 0 3.4 0',
    'M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9',
  ],
  telecharger: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm7 10 5 5 5-5', 'M12 15V3'],
  // Un fanion, pas un triangle d'alerte : signaler est une procedure
  // qualite, pas une erreur systeme. Le rendu doit rester sobre.
  signaler: ['M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z', 'M4 22v-7'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  fermer: ['M18 6 6 18', 'M6 6l12 12'],
  recherche: ['M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16', 'm21 21-4.35-4.35'],
  // Afficher / masquer un mot de passe. L'oeil BARRE signifie « masque »
  // et l'oeil ouvert « visible » : le bouton montre donc l'etat qu'il
  // FERA advenir, pas celui du champ. C'est la convention que suivent
  // les gestionnaires de mots de passe, et l'inverser desoriente.
  oeil: [
    'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z',
    'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  ],
  'oeil-barre': [
    'M9.88 9.88a3 3 0 1 0 4.24 4.24',
    'M10.73 5.08A10.4 10.4 0 0 1 12 5c7 0 10 7 10 7a13.2 13.2 0 0 1-1.67 2.68',
    'M6.61 6.61A13.5 13.5 0 0 0 2 12s3 7 10 7a9.7 9.7 0 0 0 5.39-1.61',
    'M2 2l20 20',
  ],
};

@Component({
  selector: 'app-icone',
  standalone: true,
  template: `
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      @for (trace of traces(); track trace) {
        <path [attr.d]="trace" />
      }
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      /* L'icône suit la taille du texte auquel elle est accolée : c'est
         ce qui garde l'alignement sur la ligne de base quand la taille
         de police système change (accessibilité, Dynamic Type). */
      width: var(--taille-icone, 1.25em);
      height: var(--taille-icone, 1.25em);
      flex-shrink: 0;
    }

    svg {
      width: 100%;
      height: 100%;
      display: block;
    }
  `,
})
export class IconeComponent {
  /** Nom du tracé. Un nom inconnu n'affiche rien plutôt que de casser. */
  readonly nom = input.required<string>();

  protected readonly traces = computed(() => TRACES[this.nom()] ?? []);
}
