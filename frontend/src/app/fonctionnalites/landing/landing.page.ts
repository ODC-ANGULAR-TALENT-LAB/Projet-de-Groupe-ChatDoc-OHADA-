import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { CorpusService } from '../../core/services/corpus.service';
import { IconeComponent } from '../../partage/composants/icone.component';

interface Profil {
  titre: string;
  besoin: string;
  icone: string;
}

interface Chiffre {
  libelle: string;
  valeur: string;
}

/**
 * Page d'accueil publique.
 *
 * CE QU'ELLE PROMET, ELLE DOIT POUVOIR LE TENIR. Le produit se
 * distingue d'un chatbot par une chose : chaque réponse cite l'article
 * qui la fonde, et cette citation est vérifiée mécaniquement. La page
 * montre donc une réponse réelle — question, synthèse, extrait officiel
 * — plutôt que des adjectifs.
 *
 * LES CHIFFRES DU CORPUS SONT LUS, PAS ÉCRITS. Annoncer « 3 000
 * articles » en dur se périmerait au premier chargement de texte, et une
 * page d'accueil qui ment sur son corpus décrédibilise exactement ce
 * qu'elle vend. À défaut de réponse du serveur, la carte s'efface plutôt
 * que d'afficher un nombre inventé.
 */
@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [RouterLink, IconeComponent],
  templateUrl: './landing.page.html',
  styleUrl: './landing.page.scss',
})
export class LandingPage {
  private readonly auth = inject(AuthService);
  private readonly corpus = inject(CorpusService);
  private readonly router = inject(Router);

  protected readonly profils: Profil[] = [
    {
      titre: 'Avocats et juristes',
      besoin:
        "Retrouver l'article applicable et son texte exact, prêt à être cité dans des conclusions.",
      icone: 'balance',
    },
    {
      titre: 'Experts-comptables',
      besoin:
        'Vérifier une obligation comptable ou fiscale, et joindre la référence au dossier client.',
      icone: 'corpus',
    },
    {
      titre: 'Entrepreneurs',
      besoin:
        "Comprendre ce que la loi impose avant de créer, d'embaucher ou de signer.",
      icone: 'bibliotheque',
    },
  ];

  protected readonly garanties = [
    "Chaque citation est confrontée au corpus avant d'être affichée",
    "L'assistant refuse de répondre plutôt que d'inventer",
    'Chaque texte porte sa source, sa version et sa date',
    'Export PDF sourcé, avec la version du corpus utilisée',
  ];

  protected readonly chiffres = signal<Chiffre[]>([]);

  constructor() {
    // Un visiteur déjà connecté n'a rien à faire sur une page de vente.
    if (this.auth.connecte()) {
      void this.router.navigate(['/accueil'], { replaceUrl: true });
      return;
    }
    void this.chargerChiffres();
  }

  private async chargerChiffres(): Promise<void> {
    try {
      // On lit la table de PROVENANCE et non la liste des textes :
      // elle seule porte le nombre d'articles, et c'est la même source
      // que la page Méthodologie — les deux ne peuvent pas diverger.
      const lignes = await this.corpus.provenance();
      if (!lignes.length) return;

      const articles = lignes.reduce((total, ligne) => total + ligne.articles, 0);

      this.chiffres.set([
        { libelle: 'Textes officiels', valeur: String(lignes.length) },
        {
          libelle: 'Articles en vigueur',
          valeur: articles.toLocaleString('fr-FR').replace(/\s/g, ' '),
        },
      ]);
    } catch {
      // Silence délibéré : une carte de chiffres absente vaut mieux
      // qu'un chiffre faux, et l'échec n'empêche pas de lire la page.
    }
  }
}
