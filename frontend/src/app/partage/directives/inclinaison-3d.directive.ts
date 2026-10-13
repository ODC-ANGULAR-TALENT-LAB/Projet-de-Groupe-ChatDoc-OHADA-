import { DestroyRef, Directive, ElementRef, NgZone, inject, input } from '@angular/core';

/**
 * Incline l'élément vers le pointeur, comme une carte qu'on tient en main.
 *
 * L'effet ne fait qu'écrire deux variables CSS, `--incl-x` et `--incl-y`
 * (en degrés) ; c'est la feuille de style de l'hôte qui décide quoi en
 * faire. La directive ne sait rien du dessin, et un même composant peut
 * s'incliner fort (le blason) ou à peine (une carte).
 *
 * HORS DE LA ZONE ANGULAR. `pointermove` part à chaque pixel parcouru :
 * dans la zone, chaque événement relancerait la détection de changements
 * de toute l'application — des dizaines de fois par seconde, pour une
 * valeur que le modèle n'utilise jamais. On écrit le style directement,
 * une fois par image au plus (requestAnimationFrame).
 *
 * DÉSACTIVÉE quand elle n'a pas de sens ou qu'on n'en veut pas :
 *   - au doigt (pas de survol, et le toucher ferait défiler la page) ;
 *   - quand le système demande de réduire les animations.
 */
@Directive({
  selector: '[appInclinaison3d]',
  standalone: true,
})
export class Inclinaison3dDirective {
  /** Angle maximal, en degrés, atteint au bord de l'élément. */
  readonly amplitude = input(12, { alias: 'appInclinaison3d', transform: versNombre });

  constructor() {
    const hote = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    const zone = inject(NgZone);

    const pointeurFin = matchMedia('(hover: hover) and (pointer: fine)').matches;
    const mouvementReduit = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!pointeurFin || mouvementReduit) return;

    let image = 0;
    const suivre = (e: PointerEvent) => {
      cancelAnimationFrame(image);
      image = requestAnimationFrame(() => {
        const r = hote.getBoundingClientRect();
        // -0,5 à 0,5 de part et d'autre du centre.
        const dx = (e.clientX - r.left) / r.width - 0.5;
        const dy = (e.clientY - r.top) / r.height - 0.5;
        const a = this.amplitude();
        // Le pointeur à droite fait tourner autour de l'axe vertical
        // (rotateY positif) ; en haut, autour de l'axe horizontal vers
        // l'arrière (rotateX positif). Le bord sous le pointeur recule.
        hote.style.setProperty('--incl-y', `${(dx * 2 * a).toFixed(2)}deg`);
        hote.style.setProperty('--incl-x', `${(-dy * 2 * a).toFixed(2)}deg`);
      });
    };
    const relacher = () => {
      cancelAnimationFrame(image);
      hote.style.setProperty('--incl-x', '0deg');
      hote.style.setProperty('--incl-y', '0deg');
    };

    zone.runOutsideAngular(() => {
      hote.addEventListener('pointermove', suivre);
      hote.addEventListener('pointerleave', relacher);
    });

    inject(DestroyRef).onDestroy(() => {
      cancelAnimationFrame(image);
      hote.removeEventListener('pointermove', suivre);
      hote.removeEventListener('pointerleave', relacher);
    });
  }
}

/** `appInclinaison3d` seul (attribut vide) garde l'amplitude par défaut. */
function versNombre(valeur: unknown): number {
  const n = Number(valeur);
  return valeur === '' || Number.isNaN(n) ? 12 : n;
}
