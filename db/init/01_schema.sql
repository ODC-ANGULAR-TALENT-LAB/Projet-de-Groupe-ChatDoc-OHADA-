-- =====================================================================
-- ChatDocs OHADA - schema de la base
-- Conforme au document d'architecture technique, section 4.
-- Joue automatiquement par Docker a la creation du volume pgdata.
--
-- REGLE ABSOLUE : aucun UPDATE sur le contenu d'un article.
-- Une modification legale clot l'ancienne ligne (date_abrogation)
-- et en insere une nouvelle. C'est ce qui rend l'historique
-- consultable et les retours arriere possibles.
-- =====================================================================

-- Recherche par similarite de sens (embeddings).
CREATE EXTENSION IF NOT EXISTS vector;
-- Comparaison de chaines insensible a la casse : utilise par
-- utilisateur.email, pour que "A@b.cm" et "a@b.cm" soient le meme compte.
CREATE EXTENSION IF NOT EXISTS citext;


-- ---------------------------------------------------------------------
-- CORPUS
-- ---------------------------------------------------------------------

-- Un texte officiel du corpus (un acte uniforme, un code).
-- Les colonnes de provenance ne sont pas decoratives : elles permettent
-- de remonter toute reponse contestee a sa source exacte.
CREATE TABLE texte (
    id                 SERIAL PRIMARY KEY,
    sigle              VARCHAR(20)  NOT NULL,   -- AUSCGIE, CGI, CIMA...
    titre              TEXT         NOT NULL,
    type               VARCHAR(30)  NOT NULL,   -- acte_uniforme | code
    version            VARCHAR(50)  NOT NULL,   -- "LF 2026"
    date_consolidation DATE         NOT NULL,
    source_url         TEXT,                    -- URL officielle exacte
    source_sha256      CHAR(64),                -- empreinte du PDF ingere
    valide_par         VARCHAR(120)             -- qui a relu le decoupage
);

-- Unite de decoupage du corpus : la granularite des citations.
-- Un article n'est jamais decoupe par page, toujours par article.
CREATE TABLE article (
    id                  SERIAL PRIMARY KEY,
    texte_id            INT NOT NULL REFERENCES texte(id),
    numero              VARCHAR(30) NOT NULL,  -- "92", "18 bis"
    chemin              TEXT        NOT NULL,  -- "Livre I > Titre II > Chap. 3"
    contenu             TEXT        NOT NULL,
    date_entree_vigueur DATE        NOT NULL,
    date_abrogation     DATE,                  -- NULL = en vigueur
    embedding           VECTOR(1536),
    recherche_fts       TSVECTOR
);

-- Recherche lexicale plein texte (moitie "mots exacts" de la
-- recherche hybride : numeros d'article, taux, sigles).
CREATE INDEX idx_article_fts ON article USING gin (recherche_fts);

-- La quasi-totalite des requetes filtrent sur les articles en vigueur.
CREATE INDEX idx_article_actif ON article (texte_id)
    WHERE date_abrogation IS NULL;

-- NOTE : l'index vectoriel HNSW n'est PAS cree ici. Il se construit
-- bien plus vite sur une table deja remplie (guide de realisation, B.7).
-- Il est dans db/02_index_vectoriel.sql, a jouer en fin de phase B,
-- APRES l'insertion de tous les embeddings.


-- ---------------------------------------------------------------------
-- APPLICATIF
-- ---------------------------------------------------------------------

-- Compte et quota freemium. Le quota est decompte cote serveur
-- uniquement, jamais dans le navigateur.
CREATE TABLE utilisateur (
    id                SERIAL PRIMARY KEY,
    email             CITEXT UNIQUE NOT NULL,
    -- NULL pour un compte cree via Google : il n'a pas de mot de passe.
    mot_de_passe_hash TEXT,                      -- bcrypt, cout 12
    -- Claim "sub" du jeton Google : identifiant stable du compte.
    -- L'e-mail peut changer chez Google, le sub non.
    google_sub        VARCHAR(64) UNIQUE,
    plan              VARCHAR(20) DEFAULT 'gratuit',
    quota_restant     INT         DEFAULT 5,
    quota_reinit_le   DATE,                      -- reinit par date, pas par compteur

    -- Un compte doit avoir au moins un moyen de connexion : sans cette
    -- contrainte, une ligne sans mot de passe ni google_sub serait un
    -- compte auquel personne ne peut acceder.
    CONSTRAINT utilisateur_moyen_de_connexion
        CHECK (mot_de_passe_hash IS NOT NULL OR google_sub IS NOT NULL)
);

CREATE TABLE conversation (
    id             SERIAL PRIMARY KEY,
    utilisateur_id INT REFERENCES utilisateur(id),
    titre          TEXT,
    cree_le        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE message (
    id              SERIAL PRIMARY KEY,
    conversation_id INT REFERENCES conversation(id),
    role            VARCHAR(10) NOT NULL,   -- user | assistant
    contenu         TEXT        NOT NULL,
    cree_le         TIMESTAMPTZ DEFAULT now()
);

-- Lien entre une reponse et les articles qui la fondent.
-- C'est la trace qui rend une reponse verifiable a posteriori.
CREATE TABLE citation (
    message_id INT REFERENCES message(id),
    article_id INT REFERENCES article(id),
    extrait    TEXT,
    PRIMARY KEY (message_id, article_id)
);
