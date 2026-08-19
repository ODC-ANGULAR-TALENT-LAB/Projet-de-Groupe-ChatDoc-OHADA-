import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { Jeton, Quota } from '../models';
import { ApiService } from './api.service';
import { GoogleService } from './google.service';

const CLE_JETON = 'chatdocs.jeton';

/** Compte, session et quota. Une responsabilité, un service. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly google = inject(GoogleService);
  private readonly router = inject(Router);

  readonly jeton = signal<string | null>(localStorage.getItem(CLE_JETON));
  readonly quota = signal<Quota | null>(null);
  readonly connecte = computed(() => this.jeton() !== null);

  /**
   * Crée un compte.
   *
   * `cguAcceptees` n'a pas de valeur par défaut : le serveur refuse
   * l'inscription sans acceptation, et un défaut à `true` ici
   * consentirait à la place de l'utilisateur — exactement ce que la
   * case est censée empêcher.
   */
  async inscription(
    email: string,
    motDePasse: string,
    cguAcceptees: boolean,
    prenom: string | null = null,
  ): Promise<void> {
    const jeton = await firstValueFrom(
      this.api.post<Jeton>('/auth/inscription', {
        email,
        mot_de_passe: motDePasse,
        cgu_acceptees: cguAcceptees,
        prenom,
      }),
    );
    this.enregistrer(jeton);
  }

  async connexion(email: string, motDePasse: string): Promise<void> {
    const jeton = await firstValueFrom(
      this.api.post<Jeton>('/auth/connexion', { email, mot_de_passe: motDePasse }),
    );
    this.enregistrer(jeton);
  }

  /**
   * Inscription ou connexion via Google.
   *
   * Le jeton d'identité n'est pas conservé : il sert une fois, le temps
   * que le serveur en vérifie la signature et ouvre une session. C'est
   * le jeton de l'application qui persiste ensuite.
   *
   * `cguAcceptees` n'est exigé par le serveur QUE si le compte n'existe
   * pas encore : la même route sert à s'inscrire et à se connecter, et
   * redemander l'acceptation à chaque connexion la ferait cocher sans
   * lire.
   */
  async connexionGoogle(
    jetonIdentite: string,
    cguAcceptees = false,
  ): Promise<void> {
    const jeton = await firstValueFrom(
      this.api.post<Jeton>('/auth/google', {
        jeton_identite: jetonIdentite,
        cgu_acceptees: cguAcceptees,
      }),
    );
    this.enregistrer(jeton);
  }

  /**
   * Ferme la session et ramène à la page de connexion.
   *
   * LA REDIRECTION APPARTIENT AU SERVICE, pas aux boutons. Deux boutons
   * l'appellent — la barre latérale et le menu — et se contentaient
   * d'effacer le jeton : l'utilisateur restait sur la page où il se
   * trouvait, vidée de ce qui exige une session, sans comprendre s'il
   * était encore connecté. Un troisième point d'appel aurait oublié la
   * redirection à son tour.
   *
   * `replaceUrl` retire la page authentifiée de l'historique : après une
   * déconnexion, le bouton Précédent ne doit pas y ramener.
   *
   * `redirection` n'existe que pour l'intercepteur, qui navigue lui-même
   * vers la connexion en signalant l'expiration ; sans ce drapeau, les
   * deux navigations se succéderaient et la seconde effacerait le
   * message que l'utilisateur devait lire.
   */
  deconnexion(redirection = true): void {
    localStorage.removeItem(CLE_JETON);
    this.jeton.set(null);
    this.quota.set(null);
    this.google.oublier();
    if (redirection) {
      void this.router.navigate(['/connexion'], { replaceUrl: true });
    }
  }

  /**
   * Rafraîchit le quota depuis le serveur.
   *
   * Le quota est TOUJOURS lu côté serveur, jamais décompté ici : un
   * compteur tenu par le navigateur ne protège de rien.
   */
  async rafraichirQuota(): Promise<void> {
    if (!this.connecte()) return;
    this.quota.set(await firstValueFrom(this.api.get<Quota>('/moi/quota')));
  }

  private enregistrer(jeton: Jeton): void {
    localStorage.setItem(CLE_JETON, jeton.jeton_acces);
    this.jeton.set(jeton.jeton_acces);
    void this.rafraichirQuota();
  }
}
