-- =====================================================================
-- Migration : signalement d'une reponse contestee
--
--   docker compose exec -T db psql -U chatdocs -d chatdocs \
--     < db/06_migration_signalement.sql
--
-- Idempotent.
--
-- POURQUOI CETTE TABLE. Le cahier des charges (§16 ter) fait de la
-- correction des erreurs un dispositif de PROTECTION, au meme titre que
-- les conditions d'utilisation ou l'assurance : « Assumer une erreur et
-- la corriger publiquement protege davantage qu'un silence. »
--
-- Le registre des incidents demontre la diligence de l'editeur en cas de
-- litige. Il n'a de valeur que s'il est tenu depuis le debut — un
-- registre ouvert le jour du premier litige ne prouve rien.
-- =====================================================================

CREATE TABLE IF NOT EXISTS signalement (
    id            SERIAL PRIMARY KEY,

    -- Le message conteste. On garde le lien plutot qu'une copie : la
    -- reponse, ses citations et la version du corpus utilisee restent
    -- reconstituables par la journalisation existante.
    message_id    INT NOT NULL REFERENCES message(id) ON DELETE CASCADE,
    utilisateur_id INT REFERENCES utilisateur(id),

    -- Ce que l'utilisateur reproche a la reponse.
    motif         VARCHAR(30) NOT NULL,
    commentaire   TEXT,

    -- ouvert : recu, pas encore qualifie
    -- traite  : cause identifiee et correction apportee
    -- ecarte  : signalement infonde, motif consigne
    statut        VARCHAR(20) NOT NULL DEFAULT 'ouvert',
    correction    TEXT,

    cree_le       TIMESTAMPTZ NOT NULL DEFAULT now(),
    traite_le     TIMESTAMPTZ,
    traite_par    INT REFERENCES utilisateur(id),

    CONSTRAINT signalement_motif_connu
        CHECK (motif IN ('article_faux', 'article_perime', 'hors_sujet',
                         'reponse_incomplete', 'autre')),
    CONSTRAINT signalement_statut_connu
        CHECK (statut IN ('ouvert', 'traite', 'ecarte'))
);

-- Les signalements ouverts d'abord : c'est la file de travail.
CREATE INDEX IF NOT EXISTS idx_signalement_statut
    ON signalement (statut, cree_le DESC);
