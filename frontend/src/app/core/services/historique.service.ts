import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { Conversation, ConversationDetail } from '../models';
import { ApiService } from './api.service';

/**
 * Historique des conversations.
 *
 * Le contenu des questions n'est pas exploité au-delà de cet
 * historique, et l'utilisateur peut l'effacer à tout moment :
 * c'est un engagement de confidentialité, pas une option de confort.
 */
@Injectable({ providedIn: 'root' })
export class HistoriqueService {
  private readonly api = inject(ApiService);

  readonly conversations = signal<Conversation[] | null>(null);

  async charger(): Promise<Conversation[]> {
    const liste = await firstValueFrom(
      this.api.get<Conversation[]>('/conversations'),
    );
    this.conversations.set(liste);
    return liste;
  }

  async detail(id: number): Promise<ConversationDetail> {
    return firstValueFrom(this.api.get<ConversationDetail>(`/conversations/${id}`));
  }

  async effacer(id: number): Promise<void> {
    await firstValueFrom(this.api.delete<void>(`/conversations/${id}`));
    this.conversations.update((liste) =>
      (liste ?? []).filter((conversation) => conversation.id !== id),
    );
  }
}
