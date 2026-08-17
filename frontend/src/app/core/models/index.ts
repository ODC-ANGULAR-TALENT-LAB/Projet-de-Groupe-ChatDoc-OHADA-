/**
 * Modèles partagés — miroir des schémas Pydantic du backend.
 *
 * Tout changement dans backend/app/schemas.py se répercute ici.
 */

/** Niveau de confiance rendu par l'assistant. */
export type Confiance = 'elevee' | 'moyenne' | 'insuffisante';

/**
 * Une citation VALIDÉE par le serveur.
 *
 * Le frontend ne reçoit jamais de citation non validée : le backend
 * rejette celles dont l'article n'était pas dans le contexte fourni au
 * modèle. Afficher ce bloc, c'est afficher une référence vérifiée.
 */
export interface Citation {
  article_id: number;
  sigle: string;
  numero: string;
  chemin: string;
  extrait: string;
  pourquoi?: string | null;
}

export interface ReponseChat {
  reponse: string;
  citations: Citation[];
  confiance: Confiance;
  mise_en_garde?: string | null;
  refus: boolean;
  /**
   * Vrai quand les articles sont rendus sans rédaction : le service de
   * synthèse est indisponible. Ni un refus, ni une erreur.
   */
  sans_synthese?: boolean;
  conversation_id?: number | null;
  /** Vise par l'export PDF et le signalement. */
  message_id?: number | null;
}

/** Un tour de conversation, côté affichage. */
export interface Message {
  role: 'user' | 'assistant';
  contenu: string;
  citations?: Citation[];
  confiance?: Confiance;
  miseEnGarde?: string | null;
  refus?: boolean;
  sansSynthese?: boolean;
  /** Vrai pendant la diffusion : le texte s'ecrit encore. */
  enCoursDeRedaction?: boolean;
  /** Identifiant serveur, pour exporter ou signaler cette reponse. */
  messageId?: number | null;
}

export interface Texte {
  id: number;
  sigle: string;
  titre: string;
  type: string;
  version: string;
  date_consolidation: string;
}

export interface Article {
  id: number;
  numero: string;
  chemin: string;
  contenu: string;
  date_entree_vigueur: string;
  date_abrogation?: string | null;
  texte: Texte;
  precedent_id?: number | null;
  suivant_id?: number | null;
}

/** Un nœud du sommaire : un chemin hiérarchique et ses articles. */
export interface NoeudSommaire {
  chemin: string;
  articles: { id: number; numero: string }[];
}

export interface Conversation {
  id: number;
  titre: string | null;
  cree_le: string;
}

export interface MessageHistorique {
  id: number;
  role: 'user' | 'assistant';
  contenu: string;
  cree_le: string;
  citations: Citation[];
}

export interface ConversationDetail extends Conversation {
  messages: MessageHistorique[];
}

export interface ResultatRecherche {
  id: number;
  sigle: string;
  numero: string;
  chemin: string;
  extrait: string;
  score: number;
}

export interface Quota {
  quota_restant: number;
  quota_reinit_le: string | null;
  plan: string;
  /** 'utilisateur' ou 'admin'. Décide l'accès au back-office. */
  role: string;
}

export interface Jeton {
  jeton_acces: string;
  type_jeton: string;
  expire_dans_minutes: number;
}

/**
 * Une ligne de la table de provenance.
 *
 * Source officielle, empreinte du fichier ingéré, version consolidée et
 * validateur : de quoi remonter une réponse contestée à sa source.
 */
export interface LigneProvenance {
  id: number;
  sigle: string;
  titre: string;
  type: string;
  version: string;
  date_consolidation: string;
  source_url?: string | null;
  source_sha256?: string | null;
  valide_par?: string | null;
  articles: number;
  vectorises: number;
}

export interface FaitMarquant {
  numero: string;
  resume: string;
}

/** Une publication du corpus, telle qu'elle apparaît au journal. */
export interface EntreeJournal {
  depot_id: number;
  sigle: string;
  titre: string;
  version: string;
  date_consolidation: string;
  publie_le?: string | null;
  nb_articles: number;
  ajoutes: number;
  modifies: number;
  abroges: number;
  faits_marquants: FaitMarquant[];
}
