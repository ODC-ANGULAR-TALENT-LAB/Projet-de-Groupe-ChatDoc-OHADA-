-- Le catalogue des forfaits passe du code à la base.
--
-- POURQUOI CE DÉPLACEMENT. Ajuster un prix ou un volume de crédits est
-- une décision commerciale, pas une modification de logiciel : elle ne
-- doit demander ni développeur, ni redéploiement.
--
-- CE QUI NE DOIT SURTOUT PAS SE PERDRE AU PASSAGE. Tant que le
-- catalogue vivait dans le code, un test refusait toute grille dont la
-- marge tombait sous 50 % — c'est ce qui empêchait d'ajouter des
-- crédits sans revoir le prix. Une table modifiable depuis une console
-- ne passe par aucun test : la vérification DOIT donc migrer avec elle,
-- et se faire à l'écriture, côté serveur. Sans cela, on aurait échangé
-- une garantie mécanique contre une bonne intention.
--
-- LE CODE RESTE LA SEMENCE. Les valeurs par défaut y demeurent : elles
-- alimentent cette table au premier démarrage et servent de repli si
-- elle est vide. Un déploiement neuf n'a donc pas de catalogue vide.

CREATE TABLE IF NOT EXISTS forfait (
    code           VARCHAR(30) PRIMARY KEY,
    libelle        VARCHAR(60)  NOT NULL,
    prix_fcfa      INTEGER      NOT NULL CHECK (prix_fcfa >= 0),
    credits        INTEGER      NOT NULL CHECK (credits >= 0),
    argumentaire   TEXT         NOT NULL DEFAULT '',
    -- Les arguments de vente, dans l'ordre où ils s'affichent.
    atouts         JSONB        NOT NULL DEFAULT '[]'::jsonb,
    -- Forfait d'essai : montant symbolique, exclu du plancher de marge
    -- et masqué du catalogue en production.
    essai          BOOLEAN      NOT NULL DEFAULT false,
    -- Un forfait retiré de la vente n'est pas supprimé : des comptes y
    -- sont peut-être encore abonnés, et effacer la ligne les ferait
    -- retomber sur « forfait inconnu ». On le désactive.
    actif          BOOLEAN      NOT NULL DEFAULT true,
    ordre          INTEGER      NOT NULL DEFAULT 100,
    modifie_le     TIMESTAMPTZ,
    modifie_par    INTEGER REFERENCES utilisateur (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_forfait_ordre ON forfait (ordre, code);

COMMENT ON TABLE forfait IS
    'Catalogue des forfaits, modifiable depuis la console '
    'd''administration. La marge minimale est verifiee A L''ECRITURE '
    'cote serveur : la table n''est protegee par aucun test.';

COMMENT ON COLUMN forfait.actif IS
    'false = retire de la vente mais conserve. Supprimer la ligne '
    'ferait retomber les comptes encore abonnes sur un forfait '
    'inconnu.';

COMMENT ON COLUMN forfait.essai IS
    'Montant symbolique servant a eprouver la chaine de paiement. '
    'Exclu du plancher de marge, et masque du catalogue en production.';

-- Semence : les valeurs qui vivaient dans le code. ON CONFLICT DO
-- NOTHING pour que rejouer la migration ne recrase pas un catalogue
-- deja ajuste par l'exploitant.
INSERT INTO forfait (code, libelle, prix_fcfa, credits, argumentaire, atouts, essai, ordre)
VALUES
    ('gratuit', 'Découverte', 0, 10,
     'De quoi juger l''outil sur vos propres dossiers.',
     '["10 questions par mois","Bibliothèque, recherche et calculateurs sans limite","Chaque réponse cite ses articles"]'::jsonb,
     false, 10),
    ('essentiel', 'Essentiel', 5000, 90,
     'Pour un praticien qui consulte le corpus chaque jour.',
     '["90 questions par mois","Export PDF sourcé de vos réponses","Favoris, annotations et veille sur les textes suivis"]'::jsonb,
     false, 20),
    ('cabinet', 'Cabinet', 8000, 150,
     'Pour un rythme soutenu et les dossiers à plusieurs textes.',
     '["150 questions par mois","Tout ce que contient Essentiel","Analyse de conformité et générateur de documents"]'::jsonb,
     false, 30),
    ('essai', 'Essai (test technique)', 25, 2,
     'Montant symbolique pour éprouver la chaîne de paiement. Ce forfait n''est pas destiné à la vente.',
     '["2 questions, le temps de vérifier que tout fonctionne","Débit réel de 25 FCFA sur le compte Mobile Money","Visible uniquement hors production"]'::jsonb,
     true, 90)
ON CONFLICT (code) DO NOTHING;
