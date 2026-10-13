import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * Le blason de ChatDocs OHADA, en relief.
 *
 * UN SEUL ENDROIT. La même balise <img> était recopiée six fois (barre
 * latérale, barre haute, accueil, connexion, inscription, pied de page).
 * Un effet ajouté à l'une manquait aux cinq autres ; ici, il vaut partout.
 *
 * TROIS COUCHES, aucune image en plus :
 *   1. L'ÉPAISSEUR — des ombres portées superposées, chacune décalée d'un
 *      pixel vers le bas dans un or plus sombre. Elles suivent le contour
 *      réel du dessin (drop-shadow, pas box-shadow), si bien que la plume
 *      et la balance paraissent frappées dans le métal, et non posées sur
 *      un carré.
 *   2. LE REFLET — une bande de lumière qui traverse le blason au
 *      chargement puis à chaque survol. Elle est découpée par le blason
 *      lui-même (mask-image) : la lumière n'éclaire que le métal.
 *   3. L'INCLINAISON — lue dans `--incl-x` / `--incl-y`, que pose la
 *      directive appInclinaison3d sur un parent (le lien de la marque,
 *      plus facile à survoler que l'image seule). Sans parent incliné, le
 *      blason reste de face.
 *
 * La taille vient de l'hôte : chaque page garde sa règle `.marque-blason`
 * (hauteur en em), et le blason la remplit.
 */
@Component({
  selector: 'app-blason',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'aria-hidden': 'true' },
  template: `
    <span class="volume">
      <img src="/images/blason.webp" alt="" width="131" height="162" decoding="async" />
      <span class="reflet"></span>
    </span>
  `,
  styles: `
    :host {
      display: inline-block;
      flex-shrink: 0;
      aspect-ratio: 131 / 162;
      perspective: 400px;
    }

    .volume {
      position: relative;
      display: block;
      height: 100%;
      transform-style: preserve-3d;
      transform: rotateX(var(--incl-x, 0deg)) rotateY(var(--incl-y, 0deg));
      transition: transform var(--duree-page) var(--courbe-sortie);
    }

    img {
      display: block;
      height: 100%;
      width: auto;
      filter:
        drop-shadow(0 1px 0 #a5851f)
        drop-shadow(0 1px 0 #806712)
        drop-shadow(0 1px 0 #5c4a0c)
        drop-shadow(0 4px 6px rgb(4 21 52 / 45%));
    }

    .reflet {
      position: absolute;
      inset: 0;
      pointer-events: none;
      background: linear-gradient(
        105deg,
        transparent 30%,
        rgb(255 250 225 / 85%) 48%,
        transparent 62%
      );
      background-size: 250% 100%;
      background-position: 120% 0;
      background-repeat: no-repeat;
      mask: url('/images/blason.webp') center / contain no-repeat;
      -webkit-mask: url('/images/blason.webp') center / contain no-repeat;
      mix-blend-mode: soft-light;
      animation: balayage 1.1s 0.5s var(--courbe-sortie) both;
    }

    /* Survol du lien qui contient le blason (pas seulement de l'image) :
       le reflet repasse, le blason se soulève vers le lecteur. */
    :host-context(a:hover) .reflet,
    :host-context(a:focus-visible) .reflet {
      animation: balayage 0.9s var(--courbe-sortie) both;
    }

    :host-context(a:hover) .volume {
      transform: rotateX(var(--incl-x, 0deg)) rotateY(var(--incl-y, -10deg)) translateZ(12px);
    }

    @keyframes balayage {
      from { background-position: 120% 0; }
      to { background-position: -20% 0; }
    }

    @media (prefers-reduced-motion: reduce) {
      .reflet { animation: none; opacity: 0; }
      .volume { transform: none !important; }
    }
  `,
})
export class BlasonComponent {}
