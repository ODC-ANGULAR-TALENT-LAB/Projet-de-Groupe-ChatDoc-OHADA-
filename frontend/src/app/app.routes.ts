import { Routes } from '@angular/router';

/**
 * Routes de l'application, en chargement différé par fonctionnalité.
 *
 * Ordre de construction du guide (F.2) : le chat et la lecture
 * d'article d'abord — le parcours principal — puis la bibliothèque et
 * l'historique.
 */
export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    title: "ChatDocs OHADA — le droit OHADA, preuve à l'appui",
    // `publique` retire la coquille applicative : une page qui s'adresse
    // à un visiteur ne s'affiche pas dans la barre latérale d'un outil
    // de travail. La donnée voyage avec la route, plutôt qu'une liste
    // de chemins tenue à part qui se désynchroniserait au premier
    // renommage.
    data: { publique: true },
    loadComponent: () =>
      import('./fonctionnalites/landing/landing.page').then((m) => m.LandingPage),
  },
  {
    path: 'accueil',
    title: "ChatDocs OHADA — par où commencer",
    loadComponent: () =>
      import('./fonctionnalites/accueil/accueil.page').then((m) => m.AccueilPage),
  },
  {
    path: 'connexion',
    title: 'ChatDocs OHADA — Connexion',
    data: { publique: true },
    loadComponent: () =>
      import('./fonctionnalites/auth/connexion.page').then((m) => m.ConnexionPage),
  },
  {
    path: 'inscription',
    title: 'ChatDocs OHADA — Créer un compte',
    data: { publique: true },
    loadComponent: () =>
      import('./fonctionnalites/auth/inscription.page').then(
        (m) => m.InscriptionPage,
      ),
  },
  {
    path: 'cgu',
    title: "ChatDocs OHADA — Conditions générales d'utilisation",
    // Publique : on doit pouvoir les lire AVANT de créer un compte.
    // Des conditions qu'il faudrait accepter pour pouvoir les lire
    // seraient une plaisanterie.
    data: { publique: true },
    loadComponent: () =>
      import('./fonctionnalites/legal/cgu.page').then((m) => m.CguPage),
  },
  {
    path: 'chat',
    title: 'ChatDocs OHADA — Poser une question',
    loadComponent: () =>
      import('./fonctionnalites/chat/chat.page').then((m) => m.ChatPage),
  },
  {
    path: 'article/:id',
    title: 'ChatDocs OHADA — Article',
    loadComponent: () =>
      import('./fonctionnalites/article/article.page').then((m) => m.ArticlePage),
  },
  {
    path: 'bibliotheque',
    title: 'ChatDocs OHADA — Bibliothèque',
    loadComponent: () =>
      import('./fonctionnalites/bibliotheque/bibliotheque.page').then(
        (m) => m.BibliothequePage,
      ),
  },
  {
    path: 'historique',
    title: 'ChatDocs OHADA — Historique',
    loadComponent: () =>
      import('./fonctionnalites/historique/historique.page').then(
        (m) => m.HistoriquePage,
      ),
  },
  {
    path: 'parametres',
    title: 'ChatDocs OHADA — Mon profil',
    loadComponent: () =>
      import('./fonctionnalites/parametres/parametres.page').then(
        (m) => m.ParametresPage,
      ),
  },
  {
    // /parametres a repris ce que portait cette page — e-mail, plan,
    // quota — et y a ajouté le profil et les réglages. On redirige
    // plutôt que de garder deux pages qui disent la même chose : les
    // liens déjà partagés continuent de fonctionner.
    path: 'compte',
    redirectTo: 'parametres',
    pathMatch: 'full',
  },
  {
    path: 'avis',
    title: 'ChatDocs OHADA — Votre avis',
    loadComponent: () =>
      import('./fonctionnalites/avis/avis.page').then((m) => m.AvisPage),
  },
  {
    path: 'favoris',
    title: 'ChatDocs OHADA — Mes favoris',
    loadComponent: () =>
      import('./fonctionnalites/favoris/favoris.page').then((m) => m.FavorisPage),
  },
  {
    path: 'calculateurs',
    title: 'ChatDocs OHADA — Calculateurs fiscaux',
    loadComponent: () =>
      import('./fonctionnalites/calculateurs/calculateurs.page').then(
        (m) => m.CalculateursPage,
      ),
  },
  {
    path: 'conformite',
    title: 'ChatDocs OHADA — Analyse de conformité',
    loadComponent: () =>
      import('./fonctionnalites/conformite/conformite.page').then(
        (m) => m.ConformitePage,
      ),
  },
  {
    path: 'methodologie',
    title: 'ChatDocs OHADA — Méthodologie et sources',
    loadComponent: () =>
      import('./fonctionnalites/methodologie/methodologie.page').then(
        (m) => m.MethodologiePage,
      ),
  },
  {
    path: 'journal',
    title: 'ChatDocs OHADA — Journal des mises à jour',
    loadComponent: () =>
      import('./fonctionnalites/journal/journal.page').then((m) => m.JournalPage),
  },
  {
    path: 'admin',
    title: 'ChatDocs OHADA — Administration du corpus',
    loadComponent: () =>
      import('./fonctionnalites/admin/admin.page').then((m) => m.AdminPage),
  },
  { path: '**', redirectTo: 'chat' },
];
