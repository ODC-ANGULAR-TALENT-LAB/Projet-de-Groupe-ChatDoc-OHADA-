import { ApplicationConfig, provideZoneChangeDetection, isDevMode } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  provideRouter,
  withComponentInputBinding,
  withViewTransitions,
} from '@angular/router';

import { routes } from './app.routes';
import { jwtInterceptor } from './core/interceptors/jwt.interceptor';
import { provideServiceWorker } from '@angular/service-worker';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    // withComponentInputBinding : les paramètres de route arrivent
    // directement dans les input() des pages, sans injecter
    // ActivatedRoute.
    //
    // withViewTransitions : chaque navigation passe par l'API View
    // Transitions du navigateur. L'ancienne page est photographiée, la
    // nouvelle se construit derrière, puis l'une cède la place à l'autre
    // selon les animations déclarées dans styles.scss. Un navigateur qui
    // ne connaît pas l'API (Firefox < 2025, vieux Safari) navigue comme
    // avant, sans transition : rien ne casse. La toute première page n'est
    // pas animée — on n'anime pas l'arrivée sur le site, seulement les
    // déplacements à l'intérieur.
    provideRouter(
      routes,
      withComponentInputBinding(),
      withViewTransitions({ skipInitialTransition: true }),
    ),
    provideHttpClient(withInterceptors([jwtInterceptor])), provideServiceWorker('ngsw-worker.js', {
            enabled: !isDevMode(),
            registrationStrategy: 'registerWhenStable:30000'
          }),
  ],
};
