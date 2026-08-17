-- =====================================================================
-- Index vectoriel HNSW - A JOUER EN FIN DE PHASE B
--
-- Volontairement separe du schema initial : la construction de l'index
-- sur une table deja remplie est bien plus rapide que son maintien
-- pendant des milliers d'insertions (guide de realisation, B.7).
--
-- Prerequis : tous les embeddings des articles sont inseres.
--
-- Lancement :
--   docker compose exec db psql -U chatdocs -d chatdocs \
--     -f /dev/stdin < db/02_index_vectoriel.sql
-- =====================================================================

CREATE INDEX IF NOT EXISTS idx_article_vec ON article
    USING hnsw (embedding vector_cosine_ops);
