import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ConversationDetail, Message, ReponseChat } from '../models';
import { ApiService, ErreurApi } from './api.service';
import { environnement } from '../../../environnements/environnement';
import { AuthService } from './auth.service';

/**
 * Un événement du flux SSE.
 *
 * Union discriminée plutôt qu'un objet aux champs tous optionnels :
 * c'est le type qui rend visible le fait que SEUL « fin » porte les
 * citations. Un objet permissif laisserait écrire un accès aux citations
 * sur un événement « texte » sans que rien ne le signale.
 */
type EvenementFlux =
  | { type: 'texte'; texte: string }
  | { type: 'erreur'; message: string }
  | ({ type: 'fin' } & ReponseChat);

/** Le fil de conversation. État par signals, pas de librairie externe. */
@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);

  readonly messages = signal<Message[]>([]);
  readonly enCours = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly conversationId = signal<number | null>(null);

  /**
   * Pose une question, réponse diffusée au fil de l'eau.
   *
   * Le texte se forme à l'écran pendant que le serveur rédige. Les
   * CITATIONS n'arrivent qu'à la fin, avec l'événement `fin` : elles
   * n'existent qu'après validation serveur, et en afficher une avant de
   * savoir si elle survivra au contrôle reviendrait à montrer une preuve
   * qu'on pourrait ensuite retirer.
   *
   * Passe par `fetch` et non par HttpClient : ce dernier ne rend le
   * corps qu'une fois la réponse complète, ce qui annulerait tout
   * l'intérêt du streaming.
   */
  async poser(question: string): Promise<void> {
    const propre = question.trim();
    if (!propre || this.enCours()) return;

    this.erreur.set(null);
    this.messages.update((m) => [...m, { role: 'user', contenu: propre }]);
    this.enCours.set(true);

    // La bulle de réponse est créée vide et se remplit ; son index est
    // fixe, ce qui évite de la chercher à chaque fragment.
    const index = this.messages().length;
    this.messages.update((m) => [
      ...m,
      { role: 'assistant', contenu: '', enCoursDeRedaction: true },
    ]);

    try {
      await this.lireLeFlux(propre, index);
      void this.auth.rafraichirQuota();
    } catch (erreur) {
      // La question de l'utilisateur reste affichée : on retire seulement
      // la promesse de réponse, pas ce qu'il a écrit.
      this.messages.update((m) => m.filter((_, i) => i !== index));
      this.erreur.set(
        erreur instanceof ErreurApi ? erreur.message : 'Une erreur est survenue.',
      );
    } finally {
      this.enCours.set(false);
    }
  }

  private async lireLeFlux(question: string, index: number): Promise<void> {
    const reponse = await fetch(`${environnement.urlApi}/chat/question/flux`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.auth.jeton()}`,
      },
      body: JSON.stringify({
        question,
        conversation_id: this.conversationId(),
      }),
    });

    if (!reponse.ok || !reponse.body) {
      throw new ErreurApi(
        reponse.status === 402
          ? 'Quota mensuel épuisé.'
          : 'Le service est momentanément indisponible.',
        reponse.status,
      );
    }

    const lecteur = reponse.body.getReader();
    const decodeur = new TextDecoder();
    // Un fragment réseau peut couper un événement en deux : on garde le
    // reste jusqu'à ce que la ligne vide qui le termine arrive.
    let reste = '';

    for (;;) {
      const { done, value } = await lecteur.read();
      if (done) break;

      reste += decodeur.decode(value, { stream: true });
      const evenements = reste.split('\n\n');
      reste = evenements.pop() ?? '';

      for (const evenement of evenements) {
        const ligne = evenement.split('\n').find((l) => l.startsWith('data: '));
        if (!ligne) continue;
        this.appliquer(JSON.parse(ligne.slice(6)), index);
      }
    }
  }

  private appliquer(charge: EvenementFlux, index: number): void {
    if (charge.type === 'erreur') {
      throw new ErreurApi(charge.message, 500);
    }

    if (charge.type === 'texte') {
      this.remplacer(index, { contenu: charge.texte });
      return;
    }

    // « fin » : la réponse validée remplace le texte diffusé.
    const finale = charge;
    this.conversationId.set(finale.conversation_id ?? null);
    this.remplacer(index, {
      contenu: finale.reponse,
      // Les citations arrivent déjà validées par le serveur : on les
      // affiche telles quelles, jamais reconstruites côté client.
      citations: finale.citations,
      confiance: finale.confiance,
      miseEnGarde: finale.mise_en_garde,
      refus: finale.refus,
      sansSynthese: finale.sans_synthese,
      messageId: finale.message_id,
      enCoursDeRedaction: false,
    });
  }

  private remplacer(index: number, champs: Partial<Message>): void {
    this.messages.update((m) =>
      m.map((message, i) => (i === index ? { ...message, ...champs } : message)),
    );
  }

  /**
   * Télécharge le PDF d'une réponse sourcée.
   *
   * Passe par `fetch` : le PDF arrive en binaire avec le jeton en
   * en-tête, ce qu'un simple lien ne permettrait pas.
   */
  async exporter(messageId: number): Promise<void> {
    const reponse = await fetch(
      `${environnement.urlApi}/messages/${messageId}/export`,
      { headers: { Authorization: `Bearer ${this.auth.jeton()}` } },
    );
    if (!reponse.ok) {
      this.erreur.set("L'export a échoué.");
      return;
    }

    const blob = await reponse.blob();
    const url = URL.createObjectURL(blob);
    const lien = document.createElement('a');
    lien.href = url;
    lien.download = `chatdocs-reponse-${messageId}.pdf`;
    lien.click();
    // Sans révocation, le blob reste en mémoire jusqu'au rechargement
    // de la page.
    URL.revokeObjectURL(url);
  }

  /**
   * Signale une réponse contestée.
   *
   * Ce n'est pas un aveu de faiblesse mais la procédure qualité du
   * cahier des charges (§16 ter) : le registre des incidents démontre
   * la diligence de l'éditeur, et n'a de valeur que tenu depuis le
   * début.
   */
  async signaler(
    messageId: number,
    motif: string,
    commentaire: string,
  ): Promise<void> {
    await firstValueFrom(
      this.api.post('/signalements', {
        message_id: messageId,
        motif,
        commentaire: commentaire.trim() || null,
      }),
    );
  }

  nouvelleConversation(): void {
    this.messages.set([]);
    this.conversationId.set(null);
    this.erreur.set(null);
  }

  /**
   * Reprend une conversation passée dans le fil.
   *
   * Les citations sont rechargées depuis le serveur : un échange relu
   * garde ses blocs « Base légale », et donc sa vérifiabilité. Un
   * historique dont les réponses auraient perdu leurs sources ne
   * vaudrait pas mieux qu'un chat généraliste.
   */
  reprendre(detail: ConversationDetail): void {
    this.erreur.set(null);
    this.conversationId.set(detail.id);
    this.messages.set(
      detail.messages.map((message) => ({
        role: message.role,
        contenu: message.contenu,
        citations: message.citations,
        messageId: message.id,
        // La confiance et la mise en garde ne sont pas journalisées :
        // on ne les invente pas à la relecture. Un message assistant
        // sans citation reprise s'affiche comme un refus, ce qu'il
        // était effectivement au moment de la réponse.
        refus: message.role === 'assistant' && message.citations.length === 0,
      })),
    );
  }
}
