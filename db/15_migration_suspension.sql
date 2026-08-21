-- Suspension et suppression d'un compte.
--
-- DEUX GESTES QUI NE SE VALENT PAS. Suspendre est réversible et ne
-- perd rien : le compte existe, il ne peut plus entrer. Supprimer est
-- définitif. L'administration doit disposer des deux, et la première
-- doit être le geste ordinaire.
--
-- CE QUI SURVIT À UNE SUPPRESSION, ET POURQUOI :
--
--   conversations et messages — effacés avec le compte. Ce sont ses
--     données personnelles ; les conserver après suppression irait
--     contre l'engagement de confidentialité du produit.
--
--   signalements — CONSERVÉS, auteur anonymisé. Le registre des
--     incidents est un dispositif de protection (§16 ter) : un
--     registre qu'un compte supprimé peut vider ne prouve rien le jour
--     où il faudrait s'en servir.
--
--   dépôts de corpus — LA SUPPRESSION EST BLOQUÉE. Le nom du juriste
--     qui a validé un texte figure dans la table de provenance
--     publiée : c'est la chaîne de responsabilité, et c'est elle qui
--     permet de répondre d'une citation contestée. Un compte qui a
--     déposé ou validé un texte ne se supprime donc pas — il se
--     suspend. La contrainte le refuse en base, pas seulement dans le
--     code.

ALTER TABLE utilisateur
    ADD COLUMN IF NOT EXISTS suspendu_le    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS suspendu_motif TEXT;

COMMENT ON COLUMN utilisateur.suspendu_le IS
    'NULL = compte actif. Renseignee, la connexion est refusee et les '
    'jetons existants cessent d''etre acceptes.';

COMMENT ON COLUMN utilisateur.suspendu_motif IS
    'Raison de la suspension, montree a l''administration. Suspendre '
    'sans motif rend toute reactivation arbitraire.';

-- Conversations et messages : ils partent avec le compte.
ALTER TABLE conversation DROP CONSTRAINT IF EXISTS conversation_utilisateur_id_fkey;
ALTER TABLE conversation
    ADD CONSTRAINT conversation_utilisateur_id_fkey
    FOREIGN KEY (utilisateur_id) REFERENCES utilisateur (id) ON DELETE CASCADE;

ALTER TABLE message DROP CONSTRAINT IF EXISTS message_conversation_id_fkey;
ALTER TABLE message
    ADD CONSTRAINT message_conversation_id_fkey
    FOREIGN KEY (conversation_id) REFERENCES conversation (id) ON DELETE CASCADE;

ALTER TABLE citation DROP CONSTRAINT IF EXISTS citation_message_id_fkey;
ALTER TABLE citation
    ADD CONSTRAINT citation_message_id_fkey
    FOREIGN KEY (message_id) REFERENCES message (id) ON DELETE CASCADE;

-- Signalements : le registre survit, l'auteur est anonymise.
ALTER TABLE signalement DROP CONSTRAINT IF EXISTS signalement_utilisateur_id_fkey;
ALTER TABLE signalement
    ADD CONSTRAINT signalement_utilisateur_id_fkey
    FOREIGN KEY (utilisateur_id) REFERENCES utilisateur (id) ON DELETE SET NULL;

ALTER TABLE signalement DROP CONSTRAINT IF EXISTS signalement_traite_par_fkey;
ALTER TABLE signalement
    ADD CONSTRAINT signalement_traite_par_fkey
    FOREIGN KEY (traite_par) REFERENCES utilisateur (id) ON DELETE SET NULL;

-- Depots : RESTRICT, explicitement. La suppression d'un compte qui a
-- depose ou valide un texte doit ECHOUER, pas passer en silence.
ALTER TABLE depot DROP CONSTRAINT IF EXISTS depot_depose_par_fkey;
ALTER TABLE depot
    ADD CONSTRAINT depot_depose_par_fkey
    FOREIGN KEY (depose_par) REFERENCES utilisateur (id) ON DELETE RESTRICT;

ALTER TABLE depot DROP CONSTRAINT IF EXISTS depot_decide_par_fkey;
ALTER TABLE depot
    ADD CONSTRAINT depot_decide_par_fkey
    FOREIGN KEY (decide_par) REFERENCES utilisateur (id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_utilisateur_suspendu
    ON utilisateur (suspendu_le) WHERE suspendu_le IS NOT NULL;
