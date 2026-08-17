-- =====================================================================
-- Migration : back-office d'ingestion du corpus
--
-- A JOUER SUR UNE BASE DEJA CREEE :
--   docker compose exec -T db psql -U chatdocs -d chatdocs \
--     < db/04_migration_backoffice.sql
--
-- Idempotent : peut etre rejoue sans dommage.
-- =====================================================================

-- Role : seuls les administrateurs accedent au back-office.
ALTER TABLE utilisateur
    ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'utilisateur';

ALTER TABLE utilisateur
    DROP CONSTRAINT IF EXISTS utilisateur_role_connu;
ALTER TABLE utilisateur
    ADD CONSTRAINT utilisateur_role_connu
    CHECK (role IN ('utilisateur', 'admin'));


-- ---------------------------------------------------------------------
-- Depot : un texte televerse, EN ATTENTE DE VALIDATION HUMAINE
--
-- Rien de ce qui arrive ici n'est interrogeable par les utilisateurs.
-- Un depot ne devient un texte du corpus qu'apres validation explicite
-- d'un administrateur, qui engage sa responsabilite en le validant :
-- c'est son nom qui figurera dans la table de provenance.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS depot (
    id                 SERIAL PRIMARY KEY,
    depose_par         INT NOT NULL REFERENCES utilisateur(id),

    -- Provenance, saisie par l'administrateur au moment du depot.
    -- Sans elle, le depot est refuse : ingerer un PDF dont on ignore
    -- l'origine est precisement le probleme que ce produit resout.
    nom_fichier        TEXT         NOT NULL,
    sha256             CHAR(64)     NOT NULL,
    source_url         TEXT         NOT NULL,
    sigle              VARCHAR(20)  NOT NULL,
    titre              TEXT         NOT NULL,
    type               VARCHAR(30)  NOT NULL,
    version            VARCHAR(50)  NOT NULL,
    date_consolidation DATE         NOT NULL,

    -- en_attente : decoupe, controle, mais PAS en ligne
    -- valide      : charge dans le corpus
    -- rejete      : ecarte par un administrateur
    statut             VARCHAR(20)  NOT NULL DEFAULT 'en_attente',

    -- Le decoupage et les problemes detectes, tels quels. Conserves
    -- meme apres validation : ils documentent ce qui a ete accepte.
    articles           JSONB        NOT NULL,
    problemes          JSONB        NOT NULL DEFAULT '[]'::jsonb,

    nb_pages           INT,
    extrait_par_ocr    BOOLEAN      NOT NULL DEFAULT false,

    cree_le            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    decide_le          TIMESTAMPTZ,
    decide_par         INT REFERENCES utilisateur(id),
    -- Renseigne apres validation : le texte cree dans le corpus.
    texte_id           INT REFERENCES texte(id),

    CONSTRAINT depot_statut_connu
        CHECK (statut IN ('en_attente', 'valide', 'rejete'))
);

CREATE INDEX IF NOT EXISTS idx_depot_statut ON depot (statut, cree_le DESC);

-- Un meme fichier ne peut pas etre valide deux fois : le SHA-256
-- identifie le contenu, pas le nom du fichier.
CREATE UNIQUE INDEX IF NOT EXISTS idx_depot_sha_valide
    ON depot (sha256) WHERE statut = 'valide';
