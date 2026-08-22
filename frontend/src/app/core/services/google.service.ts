import { Injectable, signal } from '@angular/core';
import { environnement } from '../../../environnements/environnement';

/** Surface minimale de la bibliothèque Google Identity Services. */
interface FenetreGoogle extends Window {
  google?: {
    accounts: {
      id: {
        initialize(config: {
          client_id: string;
          callback: (reponse: { credential: string }) => void;
          auto_select?: boolean;
          cancel_on_tap_outside?: boolean;
        }): void;
        renderButton(
          element: HTMLElement,
          options: Record<string, string | number>,
        ): void;
        disableAutoSelect(): void;
      };
    };
  };
}

const URL_SCRIPT = 'https://accounts.google.com/gsi/client';

/**
 * La page s'affiche-t-elle dans un WebView embarqué ?
 *
 * POURQUOI CETTE DÉTECTION EXISTE. Google refuse de s'authentifier
 * depuis un WebView, et c'est délibéré : sans cette règle, n'importe
 * quelle application pourrait afficher une page de connexion Google et
 * lire au passage le mot de passe de ses utilisateurs. Le bouton ne
 * s'affiche donc jamais dans notre coquille Android.
 *
 * Sans distinguer ce cas, le message d'erreur accusait l'origine non
 * déclarée — ce qui enverrait chercher pendant des heures, dans la
 * console Google Cloud, une cause qui n'existe pas.
 *
 * COMMENT ON RECONNAÎT UN WEBVIEW ANDROID. Son agent utilisateur porte
 * `; wv)` ; celui d'un vrai Chrome ne le porte pas. On exige aussi
 * `Android`, pour ne pas prendre un navigateur de bureau exotique pour
 * une application embarquée.
 */
function estWebViewEmbarque(): boolean {
  const agent = navigator.userAgent;
  return /Android/.test(agent) && /;\s*wv\)/.test(agent);
}

/**
 * Bouton « Se connecter avec Google ».
 *
 * Le navigateur obtient un jeton d'identité signé par Google, que
 * l'application transmet au serveur. Le serveur ne fait aucune
 * confiance à ce jeton : il en vérifie la signature contre les clés
 * publiques de Google avant d'ouvrir une session.
 *
 * Le script est chargé à la demande, seulement quand un écran de
 * connexion s'affiche : la bibliothèque, consultable sans compte, n'a
 * pas à contacter Google.
 */
@Injectable({ providedIn: 'root' })
export class GoogleService {
  readonly disponible = signal(false);
  readonly erreur = signal<string | null>(null);

  private chargement: Promise<void> | null = null;

  /** Charge le script Google, une seule fois pour toute la session. */
  charger(): Promise<void> {
    if (this.chargement) return this.chargement;

    this.chargement = new Promise<void>((resoudre, rejeter) => {
      if ((window as FenetreGoogle).google?.accounts?.id) {
        this.disponible.set(true);
        resoudre();
        return;
      }

      const script = document.createElement('script');
      script.src = URL_SCRIPT;
      script.async = true;
      script.defer = true;
      script.onload = () => {
        this.disponible.set(true);
        resoudre();
      };
      script.onerror = () => {
        // Réseau coupé, ou bloqueur de contenu : la connexion par mot
        // de passe reste disponible, on ne bloque pas l'utilisateur.
        this.erreur.set(
          "La connexion Google n'a pas pu être chargée. Utilisez votre " +
            'adresse e-mail et votre mot de passe.',
        );
        rejeter(new Error('script Google indisponible'));
      };
      document.head.appendChild(script);
    });

    return this.chargement;
  }

  /**
   * Affiche le bouton Google dans l'élément fourni.
   *
   * `surJeton` reçoit le jeton d'identité à transmettre au serveur.
   */
  async afficherBouton(
    hote: HTMLElement,
    surJeton: (jetonIdentite: string) => void,
  ): Promise<void> {
    await this.charger();

    const google = (window as FenetreGoogle).google;
    if (!google) return;

    google.accounts.id.initialize({
      client_id: environnement.googleClientId,
      callback: (reponse) => surJeton(reponse.credential),
      // Pas de reconnexion automatique : sur un poste partagé, elle
      // ouvrirait la session de la personne précédente.
      auto_select: false,
      cancel_on_tap_outside: true,
    });

    google.accounts.id.renderButton(hote, {
      type: 'standard',
      theme: 'outline',
      size: 'large',
      text: 'continue_with',
      shape: 'rectangular',
      locale: 'fr',
      // LARGEUR MESURÉE, PAS DEVINÉE. Une valeur figée déborde du
      // conteneur sur les écrans les plus étroits — 320 px de large
      // n'en laissent que 288 une fois le rembourrage retiré — et le
      // bouton se retrouve coupé, voire invisible si un parent masque
      // le débordement.
      //
      // Google n'accepte qu'entre 200 et 400 : hors de cet intervalle
      // le paramètre est ignoré et la largeur redevient arbitraire.
      // D'où le calage explicite plutôt qu'une confiance dans le
      // conteneur.
      width: Math.max(200, Math.min(400, hote.clientWidth || 280)),
    });

    this.verifierAffichage(hote);
  }

  /**
   * Le bouton s'est-il réellement affiché ?
   *
   * POURQUOI CE CONTRÔLE EXISTE. Quand l'origine de la page n'est pas
   * déclarée dans la console Google, `renderButton` n'échoue pas : il
   * ne dessine simplement rien, et écrit l'erreur dans la console du
   * navigateur. L'utilisateur, lui, voit un espace vide et conclut que
   * « ça ne marche pas » — sans le moindre indice.
   *
   * On constate donc l'absence de bouton, et on nomme la cause la plus
   * probable. C'est la panne la plus fréquente de cette intégration, et
   * la seule que l'application peut diagnostiquer à la place de
   * l'utilisateur.
   */
  private verifierAffichage(hote: HTMLElement): void {
    setTimeout(() => {
      if (hote.childElementCount > 0) return;

      // DEUX CAUSES POSSIBLES, ET DEUX CONDUITES A TENIR OPPOSEES.
      //
      // Dans l'application Android, le bouton ne s'affichera JAMAIS :
      // Google refuse par principe de s'authentifier depuis un WebView
      // embarqué, pour empêcher qu'une application intercepte les
      // identifiants de ses utilisateurs. Aucun réglage de notre côté
      // n'y changera rien — envoyer quelqu'un fouiller la console
      // Google Cloud le ferait chercher pendant des heures une cause
      // qui n'existe pas.
      //
      // Sur le web, l'explication habituelle est au contraire l'origine
      // non déclarée, et elle se corrige en deux minutes.
      this.erreur.set(
        estWebViewEmbarque()
          ? "La connexion Google n'est pas disponible dans l'application " +
              'Android : Google la refuse depuis une application tierce, ' +
              "par sécurité. Connectez-vous par e-mail et mot de passe, ou " +
              'ouvrez le site dans votre navigateur.'
          : "Le bouton Google ne s'est pas affiché. L'origine " +
              `${window.location.origin} doit être déclarée dans « Origines ` +
              'JavaScript autorisées » de la console Google Cloud, pour ce ' +
              "client. En attendant, l'inscription par e-mail fonctionne.",
      );
    }, 2000);
  }

  /** À appeler à la déconnexion, pour ne pas rouvrir la session seule. */
  oublier(): void {
    (window as FenetreGoogle).google?.accounts.id.disableAutoSelect();
  }
}
