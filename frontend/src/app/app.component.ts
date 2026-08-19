import { Component, computed, effect, inject, signal } from '@angular/core';
import {
  ActivatedRoute,
  NavigationEnd,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { filter } from 'rxjs/operators';
import { Conversation } from './core/models';
import { AuthService } from './core/services/auth.service';
import { ChatService } from './core/services/chat.service';
import { FavorisService } from './core/services/favoris.service';
import { ProfilService } from './core/services/profil.service';
import { HistoriqueService } from './core/services/historique.service';
import { IconeComponent } from './partage/composants/icone.component';

/**
 * Coquille de l'application.
 *
 * DEUX NAVIGATIONS, UNE SEULE SOURCE. Le poste de travail affiche la
 * barre latérale bleu nuit de la maquette ; le téléphone garde des
 * onglets en bas, que le pouce atteint sans changer de prise. Les deux
 * lisent le MÊME tableau de destinations : une entrée ajoutée apparaît
 * des deux côtés, et elles ne peuvent pas diverger.
 *
 * Le basculement se fait à 1024 px, en CSS seulement — pas de détection
 * de largeur en TypeScript, qui se tromperait au premier rendu et
 * ferait clignoter la navigation.
 */
interface Destination {
  chemin: string;
  libelle: string;
  icone: string;
  /** Réservée à ceux qui tiennent le corpus : juriste ou administrateur. */
  juriste?: boolean;
}

/** Au-delà, la barre latérale devient une liste à défiler plutôt
    qu'un repère. L'historique complet reste sur sa propre page. */
const MAX_FILS = 12;

const DESTINATIONS: Destination[] = [
  { chemin: '/chat', libelle: 'Assistant', icone: 'nouveau-chat' },
  { chemin: '/bibliotheque', libelle: 'Bibliothèque', icone: 'bibliotheque' },
  { chemin: '/historique', libelle: 'Historique', icone: 'historique' },
  { chemin: '/parametres', libelle: 'Profil', icone: 'compte' },
  { chemin: '/admin', libelle: 'Corpus', icone: 'corpus', juriste: true },
];

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, IconeComponent],
  // La classe suit l'état de la route : c'est elle qui déclenche le
  // passage de la grille applicative au flux d'une page publique.
  // Tant qu'on ne sait pas (`null`), on reste en flux : c'est l'état
  // qui correspond à « aucune coquille dessinée », donc celui qui ne
  // laisse pas de bandes vides le temps d'une image.
  host: { '[class.publique]': 'publique() !== false' },
  template: `
    <a class="evitement" href="#principal">Aller au contenu</a>

    @if (coquille()) {
    <!-- BARRE LATÉRALE — poste de travail -->
    <aside class="laterale">
      <a class="marque" routerLink="/">
        <span class="marque-nom">ChatDocs</span>
        <span class="marque-suffixe">OHADA</span>
      </a>
      <p class="marque-sous-titre">Recherche juridique sourcée</p>

      <button type="button" class="nouveau" (click)="nouvelleConversation()">
        <app-icone nom="nouveau-chat" />
        Nouvelle question
      </button>

      <nav class="liens" aria-label="Navigation principale">
        @for (destination of destinationsVisibles(); track destination.chemin) {
          <a
            [routerLink]="destination.chemin"
            routerLinkActive="actif"
            #lien="routerLinkActive"
            [attr.aria-current]="lien.isActive ? 'page' : null"
          >
            <app-icone [nom]="destination.icone" />
            {{ destination.libelle }}
          </a>
        }
      </nav>

      <!-- Les conversations récentes, reprises d'un clic. C'est ce qui
           fait d'un formulaire de questions un fil de travail : le
           cahier des charges en fait un « Must » (§5). -->
      @if (auth.connecte() && conversations().length) {
        <section class="fils" aria-label="Conversations récentes">
          <h2>Récent</h2>
          @for (conversation of conversations(); track conversation.id) {
            <button
              type="button"
              class="fil"
              [class.actif]="conversation.id === chat.conversationId()"
              (click)="reprendre(conversation.id)"
            >
              {{ conversation.titre || 'Sans titre' }}
            </button>
          }
        </section>
      }

      <!-- OUTILS. Hors de la navigation principale, non parce qu'ils
           comptent moins, mais parce que les onglets du téléphone sont
           déjà à cinq — leur maximum. On les groupe à part des pages de
           transparence : un calculateur n'est pas une page de
           référence, et les ranger ensemble brouillerait les deux. -->
      @if (auth.connecte() && profils.profil(); as moi) {
        <!-- Identité : l'avatar dit à qui appartient la session. Sans
             lui, rien ne distingue deux comptes sur le même poste. -->
        <a class="moi" routerLink="/parametres" routerLinkActive="actif">
          @if (profils.urlPhoto(moi); as url) {
            <img [src]="url" alt="" referrerpolicy="no-referrer" />
          } @else {
            <span class="initiales" aria-hidden="true">{{ moi.initiales }}</span>
          }
          <span class="moi-nom">{{ moi.prenom || moi.email }}</span>
        </a>
      }

      <nav class="secondaire" aria-label="Outils">
        <a routerLink="/favoris" routerLinkActive="actif">
          Favoris
          <!-- La pastille ne s'affiche que s'il y a réellement quelque
               chose à revoir. Un compteur à zéro affiché en permanence
               cesse d'être regardé, et le jour où il compte vraiment,
               personne ne le voit. -->
          @if (favoris.alertes().length) {
            <span class="pastille" [attr.aria-label]="
              favoris.alertes().length + ' article(s) suivi(s) ont changé'
            ">{{ favoris.alertes().length }}</span>
          }
        </a>
        <a routerLink="/calculateurs" routerLinkActive="actif">Calculateurs</a>
        <a routerLink="/conformite" routerLinkActive="actif">Conformité</a>
      </nav>

      <!-- Pages de transparence : des références, pas des destinations
           quotidiennes. -->
      <nav class="secondaire" aria-label="À propos du corpus">
        <a routerLink="/methodologie" routerLinkActive="actif">Méthodologie</a>
        <a routerLink="/journal" routerLinkActive="actif">Mises à jour</a>
      </nav>

      @if (auth.connecte()) {
        <button type="button" class="quitter" (click)="auth.deconnexion()">
          <app-icone nom="deconnexion" />
          Se déconnecter
        </button>
      }
    </aside>
    }

    @if (coquille()) {
    <!-- BARRE HAUTE — téléphone uniquement -->
    <header class="barre">
      <a class="marque" routerLink="/">
        <span class="marque-nom">ChatDocs</span>
        <span class="marque-suffixe">OHADA</span>
      </a>
      @if (auth.connecte()) {
        <button type="button" class="lien" (click)="auth.deconnexion()">
          Se déconnecter
        </button>
      }
    </header>
    }

    <main id="principal">
      <router-outlet />
    </main>

    @if (coquille()) {
    <!-- ONGLETS — téléphone uniquement -->
    <nav class="onglets" aria-label="Navigation principale">
      @for (destination of destinationsVisibles(); track destination.chemin) {
        <a
          [routerLink]="destination.chemin"
          routerLinkActive="actif"
          #onglet="routerLinkActive"
          [attr.aria-current]="onglet.isActive ? 'page' : null"
        >
          <app-icone [nom]="destination.icone" />
          {{ destination.libelle }}
        </a>
      }
    </nav>
    }
  `,
  styles: `
    :host {
      display: grid;
      grid-template-rows: auto 1fr auto;
      grid-template-areas: 'barre' 'principal' 'onglets';
      height: 100dvh;
    }

    /* Page publique : plus de coquille, donc plus de gabarit à tenir.
       Sans cette règle, la grille garderait ses trois rangées et la
       page se retrouverait coincée dans celle du milieu, avec deux
       bandes vides au-dessus et en dessous. */
    :host(.publique) {
      display: block;
      height: auto;
      min-height: 100dvh;
    }

    /* --- Barre latérale : masquée sous 1024 px ---------------------- */
    .laterale {
      display: none;
      grid-area: laterale;
      flex-direction: column;
      gap: var(--e1);
      padding: var(--e6) var(--e3);
      background: var(--bleu-nuit);
      color: var(--sur-nuit);
      box-shadow: var(--ombre-flottante);
      overflow-y: auto;
    }

    /* Flex plutôt qu'une espace dans le gabarit : Angular supprime les
       blancs entre éléments à la compilation, et « ChatDocs » et
       « OHADA » se retrouvaient soudés. */
    .marque {
      display: inline-flex;
      align-items: baseline;
      gap: 0.28em;
      font-family: var(--police-serif);
      text-decoration: none;
      line-height: 1.1;
    }

    .marque-nom {
      color: #fff;
    }

    .marque-suffixe {
      color: var(--or);
    }

    .laterale {
      .marque {
        padding: 0 var(--e2);
        font-size: 1.6rem;
        font-weight: 700;
        letter-spacing: -0.02em;
      }

      .marque-sous-titre {
        margin: var(--e1) 0 var(--e6);
        padding: 0 var(--e2);
        font-size: 0.78rem;
        color: var(--sur-nuit-faible);
      }
    }

    /* Action principale de la barre : une seule, conformément à la
       règle « un seul appel à l'action primaire par écran ». */
    .nouveau {
      display: flex;
      align-items: center;
      gap: var(--e2);
      margin-bottom: var(--e4);
      padding: 0.6rem var(--e2);
      background: transparent;
      color: var(--sur-nuit);
      border: 1px solid rgb(255 255 255 / 18%);
      border-radius: var(--rayon);
      font: inherit;
      font-size: 0.92rem;
      font-weight: 500;
      text-align: left;
      cursor: pointer;
      transition: background-color 160ms ease-out, border-color 160ms ease-out;

      &:hover,
      &:focus-visible {
        background: rgb(255 255 255 / 7%);
        border-color: var(--or);
      }
    }

    .liens {
      display: flex;
      flex-direction: column;
      gap: 2px;

      a {
        display: flex;
        align-items: center;
        gap: var(--e2);
        /* Le filet actif fait 3 px : on réserve la place des deux côtés
           pour que l'entrée ne se décale pas en devenant active. */
        padding: 0.6rem var(--e2) 0.6rem calc(var(--e2) - 3px);
        border-left: 3px solid transparent;
        border-radius: 0 var(--rayon) var(--rayon) 0;
        color: var(--sur-nuit-faible);
        font-size: 0.92rem;
        font-weight: 500;
        text-decoration: none;
        transition: background-color 160ms ease-out, color 160ms ease-out;

        &:hover {
          background: rgb(255 255 255 / 6%);
          color: var(--sur-nuit);
        }
      }

      .actif {
        background: rgb(255 255 255 / 9%);
        border-left-color: var(--or);
        color: #fff;

        app-icone {
          color: var(--or);
        }
      }
    }

    /* La liste défile ; le bouton de déconnexion reste en bas. */
    .fils {
      margin-top: var(--e4);
      padding-top: var(--e3);
      border-top: 1px solid rgb(255 255 255 / 12%);
      overflow-y: auto;
      min-height: 0;

      h2 {
        margin: 0 0 var(--e2);
        padding: 0 var(--e2);
        font-family: var(--police-interface);
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        color: var(--sur-nuit-faible);
      }
    }

    .fil {
      display: block;
      width: 100%;
      padding: 0.45rem var(--e2);
      background: none;
      border: none;
      border-radius: var(--rayon);
      color: var(--sur-nuit-faible);
      font: inherit;
      font-size: 0.85rem;
      text-align: left;
      /* Un titre de conversation est une question entière : on la coupe
         proprement plutôt que de laisser la barre s'élargir. */
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      cursor: pointer;

      &:hover {
        background: rgb(255 255 255 / 6%);
        color: var(--sur-nuit);
      }

      &.actif {
        background: rgb(255 255 255 / 9%);
        color: #fff;
      }
    }

    .secondaire {
      display: flex;
      flex-wrap: wrap;
      gap: var(--e3);
      margin-top: auto;
      padding: var(--e4) var(--e2) 0;

      a {
        color: var(--sur-nuit-faible);
        font-size: 0.78rem;
        text-decoration: none;

        &:hover,
        &.actif {
          color: var(--or);
        }
      }
    }

    /* Le second groupe suit le premier. Sans cette règle, il hérite du
       « margin-top: auto » et se décolle : les deux blocs seraient
       poussés en bas chacun de leur côté, avec un vide entre eux. */
    .moi {
      display: flex;
      align-items: center;
      gap: var(--e2);
      margin-top: var(--e4);
      padding: var(--e2);
      color: var(--sur-nuit);
      text-decoration: none;
      border-radius: var(--rayon);

      &:hover,
      &.actif {
        background: rgba(255, 255, 255, 0.07);
      }

      img,
      .initiales {
        flex-shrink: 0;
        width: 30px;
        height: 30px;
        border-radius: 50%;
        object-fit: cover;
      }

      /* Les initiales occupent exactement la place de la photo : son
         absence ne doit pas déplacer la mise en page. */
      .initiales {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.72rem;
        font-weight: 700;
        color: var(--bleu-encre);
        background: var(--or);
      }
    }

    .moi-nom {
      font-size: 0.85rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .pastille {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 18px;
      height: 18px;
      margin-left: var(--e2);
      padding: 0 5px;
      font-size: 0.68rem;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--bleu-encre);
      background: var(--or);
      border-radius: 999px;
    }

    .secondaire + .secondaire {
      margin-top: 0;
      padding-top: var(--e2);
    }

    .quitter {
      display: flex;
      align-items: center;
      gap: var(--e2);
      padding: 0.6rem var(--e2);
      background: none;
      border: none;
      border-top: 1px solid rgb(255 255 255 / 12%);
      padding-top: var(--e4);
      margin-top: var(--e3);
      color: var(--sur-nuit-faible);
      font: inherit;
      font-size: 0.88rem;
      text-align: left;
      cursor: pointer;

      &:hover,
      &:focus-visible {
        color: var(--sur-nuit);
      }
    }

    /* --- Barre haute et onglets : téléphone ------------------------- */
    .barre {
      grid-area: barre;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--e2);
      padding: 0.6rem 0.9rem;
      background: var(--bleu-nuit);
      color: #fff;

      .marque {
        font-size: 1rem;
        font-weight: 600;
      }
    }

    .lien {
      background: none;
      border: none;
      color: var(--sur-nuit);
      font: inherit;
      font-size: 0.8rem;
      text-decoration: underline;
      cursor: pointer;
    }

    main {
      grid-area: principal;
      min-height: 0;
      overflow: hidden;
    }

    .onglets {
      grid-area: onglets;
      display: flex;
      background: var(--surface);
      border-top: 1px solid var(--bordure);
      /* Marge de sécurité pour la barre d'accueil des téléphones. */
      padding-bottom: env(safe-area-inset-bottom, 0);

      a {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 0.15rem;
        /* 44 px minimum de hauteur de cible tactile. */
        min-height: 48px;
        padding: 0.45rem 0.25rem;
        font-size: 0.68rem;
        color: var(--gris-texte);
        text-decoration: none;
        border-top: 2px solid transparent;

        --taille-icone: 1.35rem;
      }

      .actif {
        color: var(--bleu-nuit);
        border-top-color: var(--or);

        app-icone {
          color: var(--or-fonce);
        }
      }
    }

    /* --- Poste de travail ------------------------------------------- */
    @media (min-width: 1024px) {
      :host {
        grid-template-rows: 1fr;
        grid-template-columns: var(--largeur-laterale) 1fr;
        grid-template-areas: 'laterale principal';
      }

      .laterale {
        display: flex;
      }

      .barre,
      .onglets {
        display: none;
      }
    }

    /* Lien d'évitement : visible seulement au clavier. */
    .evitement {
      position: absolute;
      left: -999px;

      &:focus {
        left: var(--e2);
        top: var(--e2);
        z-index: 10;
        background: var(--surface);
        padding: var(--e2);
        border-radius: var(--rayon);
      }
    }
  `,
})
export class AppComponent {
  protected readonly auth = inject(AuthService);
  protected readonly chat = inject(ChatService);
  protected readonly favoris = inject(FavorisService);
  protected readonly profils = inject(ProfilService);
  private readonly historique = inject(HistoriqueService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  /**
   * La page en cours s'adresse-t-elle à un visiteur, et non à un
   * utilisateur au travail ?
   *
   * POURQUOI PAS UNE LISTE DE CHEMINS ICI. Un tableau de type
   * `['/', '/connexion']` se désynchronise au premier renommage de
   * route, en silence. L'information appartient à la route : elle la
   * déclare par `data: { publique: true }`, et se transporte avec elle.
   */
  protected readonly publique = signal<boolean | null>(null);

  /** La coquille ne se dessine que lorsqu'on SAIT qu'elle est due.
      `null` est l'état « pas encore navigué » : afficher la barre puis
      la retirer au premier NavigationEnd produisait un clignotement
      visible à chaque arrivée sur la page d'accueil. */
  protected readonly coquille = computed(() => this.publique() === false);

  constructor() {
    void this.auth.rafraichirQuota();

    // On lit la route la PLUS PROFONDE : c'est elle qui porte la
    // donnée, et une route parente pourrait n'en avoir aucune.
    this.router.events
      .pipe(filter((evenement) => evenement instanceof NavigationEnd))
      .subscribe(() => {
        let route = this.route;
        while (route.firstChild) route = route.firstChild;
        this.publique.set(Boolean(route.snapshot.data['publique']));
      });
    // Le fil se recharge dès que l'utilisateur se connecte, et après
    // chaque échange : une conversation qui vient d'être ouverte doit
    // apparaître sans que l'utilisateur ait à recharger la page.
    effect(() => {
      this.chat.messages();
      if (this.auth.connecte()) {
        void this.historique.charger();
        void this.favoris.rafraichirAlertes();
        // Le profil porte le prénom et l'avatar : il est chargé une
        // fois pour toute l'application, pas par chaque page.
        if (!this.profils.profil()) void this.profils.charger();
      }
    });
  }

  protected conversations(): Conversation[] {
    return (this.historique.conversations() ?? []).slice(0, MAX_FILS);
  }

  protected async reprendre(id: number): Promise<void> {
    this.chat.reprendre(await this.historique.detail(id));
    void this.router.navigate(['/chat']);
  }

  /** L'onglet Corpus n'apparaît que pour un juriste ou un administrateur.
      Le serveur refuse de toute façon les routes /admin aux autres :
      masquer n'est pas protéger, c'est juste ne pas encombrer. */
  protected destinationsVisibles(): Destination[] {
    const role = this.auth.quota()?.role;
    const tientLeCorpus = role === 'juriste' || role === 'admin';
    return DESTINATIONS.filter((destination) => !destination.juriste || tientLeCorpus);
  }

  protected nouvelleConversation(): void {
    this.chat.nouvelleConversation();
    void this.router.navigate(['/chat']);
  }
}
