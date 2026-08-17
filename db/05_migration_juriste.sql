-- =====================================================================
-- Migration : le compte juriste
--
-- A JOUER SUR UNE BASE DEJA CREEE :
--   docker compose exec -T db psql -U chatdocs -d chatdocs \
--     < db/05_migration_juriste.sql
--
-- Idempotent : peut etre rejoue sans dommage.
--
-- POURQUOI UN TROISIEME ROLE. Le cahier des charges distingue deux
-- responsabilites que le role 'admin' confondait :
--
--   - tenir le corpus a jour, et ENGAGER SA SIGNATURE en validant un
--     texte : c'est un acte professionnel, pas un acte technique. Le
--     nom du validateur figure dans la table de provenance publiee, et
--     c'est lui qui repond d'une citation contestee (§2 ter et §16 ter).
--   - administrer l'application : attribuer les roles, surveiller.
--
-- Un juriste n'a aucune raison de pouvoir promouvoir un compte ; un
-- administrateur systeme n'a aucune legitimite a valider un texte de
-- loi. D'ou deux roles distincts, et non un seul cumulant tout.
-- =====================================================================

ALTER TABLE utilisateur
    DROP CONSTRAINT IF EXISTS utilisateur_role_connu;
ALTER TABLE utilisateur
    ADD CONSTRAINT utilisateur_role_connu
    CHECK (role IN ('utilisateur', 'juriste', 'admin'));


-- ---------------------------------------------------------------------
-- Analyse d'un depot : ce que le diff et l'IA ont produit
--
-- Fige EN BASE, comme le decoupage et les controles : l'analyse doit
-- rester consultable apres coup, exactement telle qu'elle a ete montree
-- au juriste au moment ou il a valide. Sans cela, impossible de
-- reconstituer sur quoi il s'est prononce.
-- ---------------------------------------------------------------------
-- Nom de colonne : `analyse_diff` et non `analyse`. ANALYSE est un mot
-- reserve de PostgreSQL (synonyme d'ANALYZE) : la colonne serait a
-- proteger par des guillemets dans chaque requete, et la premiere fois
-- qu'on l'oublierait donnerait une erreur de syntaxe obscure.
ALTER TABLE depot
    ADD COLUMN IF NOT EXISTS analyse_diff JSONB;

-- Articles effectivement retenus par le juriste, quand il ne valide
-- qu'une partie du depot. NULL = tout le depot (comportement d'avant).
ALTER TABLE depot
    ADD COLUMN IF NOT EXISTS articles_retenus JSONB;


-- ---------------------------------------------------------------------
-- Le versionnement, enfin utilise
--
-- date_abrogation existe depuis le schema initial mais n'a jamais ete
-- ecrite : rien ne cloturait un article. La validation d'une version
-- modifiee le fera desormais. Cet index sert la recherche, qui ne doit
-- remonter que les articles EN VIGUEUR.
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_article_en_vigueur
    ON article (texte_id) WHERE date_abrogation IS NULL;
