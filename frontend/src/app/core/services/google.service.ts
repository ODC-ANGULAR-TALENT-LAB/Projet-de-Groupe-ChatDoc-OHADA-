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
      width: 280,
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
      this.erreur.set(
        "Le bouton Google ne s'est pas affiché. L'origine " +
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
