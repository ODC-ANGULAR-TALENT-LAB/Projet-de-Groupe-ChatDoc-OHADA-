-- =====================================================================
-- Migration : connexion par compte Google
--
-- A JOUER SUR UNE BASE DEJA CREEE. Les scripts de db/init/ ne sont
-- executes qu'a la creation du volume ; une base existante ne les
-- rejoue jamais.
--
--   docker compose exec -T db psql -U chatdocs -d chatdocs \
--     < db/03_migration_google.sql
--
-- Idempotent : peut etre rejoue sans dommage.
-- =====================================================================

-- Identifiant stable du compte Google (claim "sub" du jeton).
-- L'adresse e-mail peut changer chez Google, pas le sub : c'est lui qui
-- identifie le compte de facon durable.
ALTER TABLE utilisateur
    ADD COLUMN IF NOT EXISTS google_sub VARCHAR(64) UNIQUE;

-- Un compte cree via Google n'a pas de mot de passe. La colonne doit
-- donc accepter NULL, ce que le schema initial interdisait.
ALTER TABLE utilisateur
    ALTER COLUMN mot_de_passe_hash DROP NOT NULL;

-- Garde-fou : un compte doit avoir au moins un moyen de connexion.
-- Sans cette contrainte, une ligne sans mot de passe NI google_sub
-- serait un compte auquel personne ne peut acceder.
ALTER TABLE utilisateur
    DROP CONSTRAINT IF EXISTS utilisateur_moyen_de_connexion;
ALTER TABLE utilisateur
    ADD CONSTRAINT utilisateur_moyen_de_connexion
    CHECK (mot_de_passe_hash IS NOT NULL OR google_sub IS NOT NULL);
