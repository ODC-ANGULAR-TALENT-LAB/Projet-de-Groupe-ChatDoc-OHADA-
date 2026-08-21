import {
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
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
/**
 * À QUI S'ADRESSE UNE DESTINATION.
 *
 *   client    — fonctionnalité de service : elle n'a aucun sens pour un
 *               compte d'exploitation, qui n'a ni forfait, ni crédits,
 *               ni dossiers personnels à suivre.
 *   personnel — outil de travail du juriste ou de l'administrateur.
 *   tous      — utile aux deux.
 *
 * SANS CE CHAMP, un administrateur voyait Favoris, Calculateurs,
 * Conformité, Forfaits et « Votre avis » : des fonctions de client,
 * dans un compte qui n'en est pas un. Le drapeau dit l'intention, là
 * où une liste de chemins tenue à part se serait désynchronisée au
 * premier renommage.
 */
type Audience = 'client' | 'personnel' | 'tous';

interface Destination {
  chemin: string;
  libelle: string;
  icone: string;
  audience: Audience;
  /** Réservée à l'administration du service. Le juriste ne l'a PAS :
      il tient le corpus, il ne distribue pas les droits. */
  admin?: boolean;
}

/** Au-delà, la barre latérale devient une liste à défiler plutôt
    qu'un repère. L'historique complet reste sur sa propre page. */
const MAX_FILS = 12;

const DESTINATIONS: Destination[] = [
  // L'assistant et la bibliothèque servent aux deux : le juriste doit
  // pouvoir interroger l'assistant pour vérifier que le texte qu'il
  // vient de déposer produit les bonnes citations. C'est son outil de
  // contrôle, pas une commodité.
  { chemin: '/chat', libelle: 'Assistant', icone: 'nouveau-chat', audience: 'tous' },
  {
    chemin: '/bibliotheque',
    libelle: 'Bibliothèque',
    icone: 'bibliotheque',
    audience: 'tous',
  },
  // L'historique suit des dossiers personnels : c'est un usage client.
  {
    chemin: '/historique',
    libelle: 'Historique',
    icone: 'historique',
    audience: 'client',
  },
  { chemin: '/parametres', libelle: 'Profil', icone: 'compte', audience: 'tous' },
  {
    chemin: '/admin',
    libelle: 'Corpus',
    icone: 'corpus',
    audience: 'personnel',
  },
  {
    chemin: '/administration',
    libelle: 'Administration',
    icone: 'compte',
    audience: 'personnel',
    admin: true,
  },
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
  host: {
    '[class.publique]': 'publique() !== false',
    // ÉCHAPPEMENT. Une feuille modale doit se fermer à la touche Échap :
    // c'est le seul recours au clavier, et le voile n'est pas
    // atteignable par tabulation.
    '(document:keydown.escape)': 'fermerMenu()',
  },
  template: `
    <a class="evitement" href="#principal">Aller au contenu</a>

    @if (coquille()) {
    <!-- BARRE LATÉRALE — poste de travail -->
    <aside class="laterale">
      <a class="marque" routerLink="/">
        <img
          class="marque-blason"
          src="/images/blason.webp"
          alt=""
          width="131"
          height="162"
        />
        <span class="marque-texte">
          <span class="marque-nom">ChatDocs</span>
          <span class="marque-suffixe">OHADA</span>
        </span>
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

      <!-- OUTILS DU CLIENT. Favoris, calculateurs et conformité suivent
           des dossiers : un compte d'exploitation n'en a aucun, et les
           lui proposer laisse croire qu'il lui manque quelque chose. -->
      @if (!estPersonnel()) {
      <nav class="nav-outils" aria-label="Outils">
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
      }

      <!-- Pages de transparence : des références, pas des destinations
           quotidiennes. « Votre avis » les rejoint parce qu'on n'y va
           pas non plus tous les jours — mais il faut pouvoir le trouver
           sans passer par les réglages du compte. -->
      <nav class="nav-outils" aria-label="À propos">
        <!-- Forfaits et avis sont des pages de client : le premier
             vend des crédits, le second demande son opinion sur le
             service à celui qui le rend. Méthodologie et mises à jour
             restent : ce sont des pages de transparence sur le corpus,
             utiles à tous. -->
        @if (!estPersonnel()) {
          <a routerLink="/forfaits" routerLinkActive="actif">Forfaits</a>
        }
        <a routerLink="/methodologie" routerLinkActive="actif">Méthodologie</a>
        <a routerLink="/journal" routerLinkActive="actif">Mises à jour</a>
        @if (auth.connecte() && !estPersonnel()) {
          <a routerLink="/avis" routerLinkActive="actif">Votre avis</a>
        }
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
        <img
          class="marque-blason"
          src="/images/blason.webp"
          alt=""
          width="131"
          height="162"
        />
        <span class="marque-texte">
          <span class="marque-nom">ChatDocs</span>
          <span class="marque-suffixe">OHADA</span>
        </span>
      </a>
      <!-- PAS DE DÉCONNEXION ICI. Elle vit desormais dans la feuille
           « Plus », avec le reste de ce que la barre latérale contient.
           La dupliquer donnerait deux chemins pour un geste que l'on
           fait une fois par session, et laisserait la barre haute
           encombrée alors qu'elle ne sert plus qu'à identifier le
           produit. -->
    </header>
    }

    <main id="principal">
      <router-outlet />
    </main>

    @if (coquille()) {
    <!-- ONGLETS — téléphone uniquement -->
    <nav class="onglets" aria-label="Navigation principale">
      @for (destination of destinationsOnglets(); track destination.chemin) {
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
      <!-- LA CINQUIÈME PLACE EST TOUJOURS « PLUS ». Elle n'est pas
           l'une des destinations : c'est la porte de tout ce que la
           barre latérale montre sur poste de travail et que le
           téléphone n'avait aucun moyen d'atteindre. -->
      <button
        type="button"
        class="plus"
        [class.actif]="menuOuvert()"
        [attr.aria-expanded]="menuOuvert()"
        aria-controls="menu-mobile"
        aria-haspopup="dialog"
        (click)="basculerMenu()"
      >
        <app-icone [nom]="menuOuvert() ? 'fermer' : 'menu'" />
        Plus
      </button>
    </nav>

    @if (menuOuvert()) {
      <!-- Le voile ferme au toucher : sur téléphone, c'est le geste que
           tout le monde tente en premier, avant de chercher une croix. -->
      <div class="voile-menu" (click)="fermerMenu()"></div>

      <div
        class="feuille"
        id="menu-mobile"
        role="dialog"
        aria-modal="true"
        aria-label="Menu"
        tabindex="-1"
        #feuille
      >
        <div class="feuille-poignee" aria-hidden="true"></div>

        @if (destinationsMenu().length) {
          <p class="feuille-titre">Navigation</p>
          <div class="feuille-liens">
            @for (destination of destinationsMenu(); track destination.chemin) {
              <a
                [routerLink]="destination.chemin"
                routerLinkActive="actif"
                (click)="fermerMenu()"
              >
                <app-icone [nom]="destination.icone" />
                {{ destination.libelle }}
              </a>
            }
          </div>
        }

        @if (!estPersonnel()) {
          <p class="feuille-titre">Outils</p>
          <div class="feuille-liens">
            <a routerLink="/favoris" routerLinkActive="actif" (click)="fermerMenu()">
              <app-icone nom="favori" />
              Favoris
              @if (favoris.alertes().length) {
                <span class="pastille" [attr.aria-label]="
                  favoris.alertes().length + ' article(s) suivi(s) ont changé'
                ">{{ favoris.alertes().length }}</span>
              }
            </a>
            <a routerLink="/calculateurs" routerLinkActive="actif" (click)="fermerMenu()">
              <app-icone nom="balance" />
              Calculateurs
            </a>
            <a routerLink="/conformite" routerLinkActive="actif" (click)="fermerMenu()">
              <app-icone nom="valide" />
              Conformité
            </a>
          </div>
        }

        <p class="feuille-titre">À propos</p>
        <div class="feuille-liens">
          @if (!estPersonnel()) {
            <a routerLink="/forfaits" routerLinkActive="actif" (click)="fermerMenu()">
              <app-icone nom="compte" />
              Forfaits
            </a>
          }
          <!-- « corpus » et non « balance » : la balance est déjà celle
               des calculateurs, quelques lignes plus haut. Deux entrées
               voisines partageant une icône se confondent au coup
               d'oeil, qui est le seul dont on dispose sur téléphone. -->
          <a routerLink="/methodologie" routerLinkActive="actif" (click)="fermerMenu()">
            <app-icone nom="corpus" />
            Méthodologie
          </a>
          <a routerLink="/journal" routerLinkActive="actif" (click)="fermerMenu()">
            <app-icone nom="historique" />
            Mises à jour
          </a>
          @if (auth.connecte() && !estPersonnel()) {
            <a routerLink="/avis" routerLinkActive="actif" (click)="fermerMenu()">
              <app-icone nom="signaler" />
              Votre avis
            </a>
          }
        </div>

        @if (auth.connecte()) {
          <button type="button" class="feuille-quitter" (click)="quitter()">
            <app-icone nom="deconnexion" />
            Se déconnecter
          </button>
        }
      </div>
    }
    }
  `,
  styles: `
    :host {
      display: grid;
      grid-template-rows: auto 1fr auto;
      grid-template-areas: 'barre' 'principal' 'onglets';
      height: 100dvh;

      /* Hauteur de la barre d'onglets, en un seul endroit. La barre la
         pose, la feuille « Plus » s'y arrête : les deux ne peuvent plus
         diverger. 3.7rem laisse 44 px de cible tactile une fois le
         liseré et le rembourrage retirés. */
      --h-onglets: 3.7rem;
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

    .marque {
      display: inline-flex;
      align-items: center;
      gap: 0.45em;
      font-family: var(--police-serif);
      text-decoration: none;
      line-height: 1.1;
    }

    /* Le blason se dimensionne en « em » : il suit la taille du
       mot-image partout où celui-ci change (1.6rem dans la barre
       latérale, plus petit sur téléphone) sans double réglage. */
    .marque-blason {
      height: 2.1em;
      width: auto;
      flex-shrink: 0;
    }

    /* Flex plutôt qu'une espace dans le gabarit : Angular supprime les
       blancs entre éléments à la compilation, et « ChatDocs » et
       « OHADA » se retrouvaient soudés. */
    .marque-texte {
      display: inline-flex;
      align-items: baseline;
      gap: 0.28em;
    }

    .marque-nom {
      color: #fff;
    }

    .marque-suffixe {
      color: var(--or);
    }

    .laterale {
      /* 1.3rem et non 1.6 : la barre est large de 280 px, et le nom
         devait desormais partager cette largeur avec le blason. A la
         taille precedente, l'ensemble depassait et le mot-image sortait
         de la barre. */
      .marque {
        padding: 0 var(--e2);
        font-size: var(--t-2xl);
        font-weight: 700;
        letter-spacing: -0.02em;
        /* Ceinture et bretelles : si la largeur venait a manquer de
           nouveau — police systeme differente, texte traduit — le nom
           passe a la ligne au lieu de deborder. Une marque sur deux
           lignes reste lisible ; une marque coupee, non. */
        max-width: 100%;
        flex-wrap: wrap;
      }

      .marque-sous-titre {
        margin: var(--e1) 0 var(--e6);
        padding: 0 var(--e2);
        font-size: var(--t-xs);
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
      font-size: var(--t-md);
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
        font-size: var(--t-md);
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
        font-size: var(--t-xs);
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
      font-size: var(--t-md);
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

    /* RENOMMÉ DEPUIS « .secondaire », qui est le nom d'une VARIANTE DE
       BOUTON définie globalement. Les deux se disputaient la même
       classe : le bloc de navigation héritait du socle de bouton —
       bordure, hauteur minimale de 44 px, remplissage — sans que rien
       ne le signale. Un nom de classe qui décrit un rôle ne doit pas
       servir à deux rôles. */
    .nav-outils {
      display: flex;
      flex-wrap: wrap;
      gap: var(--e3);
      margin-top: auto;
      padding: var(--e4) var(--e2) 0;

      a {
        color: var(--sur-nuit-faible);
        font-size: var(--t-xs);
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
        font-size: var(--t-xs);
        font-weight: 700;
        color: var(--bleu-encre);
        background: var(--or);
      }
    }

    .moi-nom {
      font-size: var(--t-md);
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
      font-size: var(--t-xs);
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--bleu-encre);
      background: var(--or);
      border-radius: 999px;
    }

    .nav-outils + .nav-outils {
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
      font-size: var(--t-md);
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
        font-size: var(--t-lg);
        font-weight: 600;
      }
    }

    /* Seule la couleur change : la barre haute est bleu nuit, et le gris
       du lien partagé y tomberait sous le seuil de contraste. Tout le
       reste — hauteur tactile, graisse, soulignement — vient de
       styles.scss, pour que ce bouton reste le même que les autres. */
    .lien {
      color: var(--sur-nuit);

      &:hover:not(:disabled) {
        color: var(--or);
      }
    }

    main {
      grid-area: principal;
      min-height: 0;

      /* « hidden » ici COUPAIT purement et simplement les pages longues.
         main est la rangée 1fr d'une grille haute de 100dvh : tout ce
         qui dépassait la hauteur de l'écran devenait inatteignable,
         sans barre de défilement pour y accéder. Un article de 19 000
         caractères — l'article 7 du CGI — s'arrêtait au bas de l'écran.

         « auto » ne rompt pas le chat, qui fait height: 100% et gère
         son propre défilement pour garder la zone de saisie en bas : à
         hauteur exacte il ne déborde pas, donc aucune barre n'apparaît
         et aucun défilement ne s'imbrique. */
      overflow-y: auto;
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
        /* HAUTEUR FIXE, PAS UN MINIMUM. La feuille « Plus » doit
           s'arrêter exactement au-dessus de cette barre ; avec un
           min-height, la hauteur réelle dépend du contenu — mesurée à
           59 px là où le nombre écrit en dur disait 48 — et la feuille
           la recouvrait de onze pixels, en mangeant le liseré doré qui
           signale l'onglet courant. Une seule variable donne désormais
           la mesure aux deux. */
        height: var(--h-onglets);
        padding: 0.45rem 0.25rem;
        font-size: var(--t-xs);
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
    /* Le bouton « Plus » doit être indiscernable d'un onglet : il occupe
       la même place, la même largeur, la même cible tactile. Un bouton
       qui se distingue visuellement de ses voisins passe pour un
       contrôle d'une autre nature, et se touche moins. */
    .onglets .plus {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 0.15rem;
      height: var(--h-onglets);
      padding: 0.45rem 0.25rem;
      font-family: inherit;
      font-size: var(--t-xs);
      color: var(--gris-texte);
      background: none;
      border: none;
      border-top: 2px solid transparent;
      cursor: pointer;

      --taille-icone: 1.35rem;
    }

    .voile-menu {
      position: fixed;
      inset: 0;
      /* Sous la feuille, au-dessus de tout le reste. */
      z-index: 40;
      background: rgb(27 42 74 / 45%);
    }

    .feuille {
      position: fixed;
      /* Elle s'arrête AU-DESSUS de la barre d'onglets : le bouton qui
         l'a ouverte reste visible, et l'on voit où l'on retourne en le
         touchant à nouveau. */
      inset: auto 0 calc(var(--h-onglets) + env(safe-area-inset-bottom, 0px)) 0;
      z-index: 41;
      max-height: 70vh;
      overflow-y: auto;
      padding: var(--e2) var(--e3) var(--e3);
      background: var(--surface);
      border-top: 1px solid var(--bordure);
      border-radius: var(--rayon) var(--rayon) 0 0;
      box-shadow: 0 -8px 24px rgb(27 42 74 / 18%);
      animation: monter 180ms ease-out;
    }

    /* Le glissement dit d'où vient la feuille. Sans lui, elle
       apparaît d'un coup et l'on ne sait pas si l'on a ouvert un
       panneau ou changé de page. */
    @keyframes monter {
      from {
        transform: translateY(12%);
        opacity: 0;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .feuille {
        animation: none;
      }
    }

    .feuille-poignee {
      width: 2.5rem;
      height: 0.25rem;
      margin: 0 auto var(--e2);
      background: var(--bordure);
      border-radius: 999px;
    }

    .feuille-titre {
      margin: var(--e2) 0 var(--e1);
      font-size: var(--t-xs);
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--gris-texte);
    }

    .feuille-liens {
      display: flex;
      flex-direction: column;

      a {
        display: flex;
        align-items: center;
        gap: var(--e2);
        /* 44 px : même seuil que partout ailleurs. Une liste dense est
           le premier endroit où l'on se trompe de ligne. */
        min-height: 44px;
        padding: 0 var(--e1);
        color: var(--bleu-nuit);
        text-decoration: none;
        border-radius: var(--rayon);

        --taille-icone: 1.15rem;
      }

      .actif {
        background: var(--papier);
        font-weight: 600;

        app-icone {
          color: var(--or-fonce);
        }
      }
    }

    .feuille-quitter {
      display: flex;
      align-items: center;
      gap: var(--e2);
      width: 100%;
      min-height: 44px;
      margin-top: var(--e3);
      padding: 0 var(--e1);
      font-family: inherit;
      font-size: inherit;
      color: var(--gris-texte);
      background: none;
      border: none;
      border-top: 1px solid var(--bordure);
      padding-top: var(--e2);
      cursor: pointer;

      --taille-icone: 1.15rem;
    }

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

      /* SUR POSTE DE TRAVAIL, LA FEUILLE N'EXISTE PAS. La barre
         latérale montre déjà tout ce qu'elle contient ; si un
         redimensionnement de fenêtre la laissait ouverte, elle
         masquerait le contenu sans qu'aucun bouton visible ne
         permette de la refermer — celui qui l'a ouverte est caché. */
      .voile-menu,
      .feuille {
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

  /**
   * La feuille « Plus » est-elle ouverte ?
   *
   * ELLE NE VIT QUE SUR TÉLÉPHONE. Le CSS la masque au-delà de
   * 1024 px : sur poste de travail, la barre latérale montre déjà tout
   * ce qu'elle contient.
   */
  protected readonly menuOuvert = signal(false);

  private readonly feuille = viewChild<ElementRef<HTMLElement>>('feuille');

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
        // La feuille se referme à l'arrivée. Les liens la ferment déjà
        // eux-mêmes, mais pas le bouton « précédent » du téléphone :
        // sans cela, un retour en arrière rouvrait la page derrière une
        // feuille restée ouverte.
        this.menuOuvert.set(false);
      });

    // LE FOCUS SUIT LA FEUILLE. Sans ce déplacement, la tabulation
    // reprend au début de la page et la lecture d'écran continue
    // d'annoncer le contenu masqué : la feuille est visible à l'oeil,
    // absente pour tout le reste.
    effect(() => {
      if (this.menuOuvert()) this.feuille()?.nativeElement.focus();
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
  /**
   * Les destinations que ce compte doit voir.
   *
   * DEUX SENS, ET C'EST LE POINT. Un client ne voit pas les outils
   * d'exploitation — c'était déjà le cas. Mais un compte
   * d'exploitation ne doit pas davantage voir les fonctions de client :
   * il n'a ni forfait, ni crédits, ni dossiers à suivre, et lui
   * proposer « Favoris » ou « Forfaits » laisse croire qu'il lui manque
   * quelque chose alors que ces pages ne le concernent pas.
   */
  protected destinationsVisibles(): Destination[] {
    const role = this.auth.quota()?.role;
    const personnel = role === 'juriste' || role === 'admin';
    const administre = role === 'admin';

    return DESTINATIONS.filter((destination) => {
      if (destination.admin && !administre) return false;
      if (destination.audience === 'personnel') return personnel;
      if (destination.audience === 'client') return !personnel;
      return true;
    });
  }

  /** Ce compte sert-il à exploiter le service plutôt qu'à s'en servir ? */
  protected estPersonnel(): boolean {
    const role = this.auth.quota()?.role;
    return role === 'juriste' || role === 'admin';
  }

  /**
   * Les destinations qui tiennent dans la barre du bas.
   *
   * QUATRE, ET NON CINQ. Cinq reste le maximum tenable — au-delà, les
   * libellés se tronquent et les cibles tactiles passent sous le seuil
   * confortable. Mais la cinquième place revient à « Plus », qui donne
   * accès à tout le reste : sans elle, un administrateur voyait ses
   * cinq destinations et RIEN d'autre, pendant que Favoris,
   * Calculateurs, Conformité, Forfaits, Méthodologie, Mises à jour et
   * « Votre avis » restaient hors d'atteinte sur téléphone.
   *
   * On coupe la FIN plutôt que le début : les premières entrées sont
   * les gestes quotidiens.
   */
  protected destinationsOnglets(): Destination[] {
    return this.destinationsVisibles().slice(0, 4);
  }

  /** Les destinations que la barre n'a pas pu montrer. */
  protected destinationsMenu(): Destination[] {
    return this.destinationsVisibles().slice(4);
  }

  protected basculerMenu(): void {
    this.menuOuvert.update((ouvert) => !ouvert);
  }

  protected fermerMenu(): void {
    this.menuOuvert.set(false);
  }

  /** Fermer AVANT de partir : la déconnexion redirige vers la page de
      connexion, et une feuille laissée ouverte s'y afficherait par-dessus. */
  protected quitter(): void {
    this.fermerMenu();
    this.auth.deconnexion();
  }

  protected nouvelleConversation(): void {
    this.chat.nouvelleConversation();
    void this.router.navigate(['/chat']);
  }
}
