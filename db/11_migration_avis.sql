-- Avis des utilisateurs sur l'application.
--
-- UN SEUL AVIS PAR COMPTE, RÉVISABLE. Un utilisateur a une opinion sur
-- le produit, pas une collection d'opinions. Autoriser plusieurs avis
-- par personne transformerait la page en fil de discussion et fausserait
-- toute moyenne : celui qui revient trois fois pèserait trois fois.
-- D'où la contrainte d'unicité, et un enregistrement en UPSERT.
--
-- CE N'EST PAS UN RETOUR SUR UNE RÉPONSE. L'avis porte sur
-- l'application dans son ensemble. Juger la qualité d'une réponse
-- donnée demanderait de rattacher le retour à la question, aux articles
-- cités et à la réponse produite — un tout autre objet, qui reste à
-- construire si le besoin apparaît.
--
-- SUPPRESSION EN CASCADE. Un compte supprimé emporte son avis : le
-- conserver laisserait un commentaire nominatif orphelin, que plus
-- personne ne pourrait retirer.

CREATE TABLE IF NOT EXISTS avis (
    id             SERIAL PRIMARY KEY,
    utilisateur_id INTEGER     NOT NULL
                   REFERENCES utilisateur (id) ON DELETE CASCADE,
    note           SMALLINT    NOT NULL CHECK (note BETWEEN 1 AND 5),
    commentaire    TEXT,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le     TIMESTAMPTZ,
    CONSTRAINT avis_un_par_utilisateur UNIQUE (utilisateur_id)
);

-- L'administration lit les avis du plus récent au plus ancien : c'est
-- le seul ordre utile pour surveiller ce qui remonte.
CREATE INDEX IF NOT EXISTS idx_avis_recents
    ON avis (COALESCE(modifie_le, cree_le) DESC);

COMMENT ON TABLE avis IS
    'Avis d''un utilisateur sur l''application : note sur 5 et '
    'commentaire libre. Un seul par compte, modifiable.';

COMMENT ON COLUMN avis.note IS
    'Note de 1 a 5. La contrainte vit ici et non seulement dans l''API : '
    'une note hors bornes rendrait toute moyenne fausse sans que rien '
    'ne le signale.';

COMMENT ON COLUMN avis.modifie_le IS
    'NULL tant que l''avis n''a pas ete revu. Distingue un avis donne '
    'une fois d''un avis reconsidere, ce que la seule date de creation '
    'ne dirait pas.';
