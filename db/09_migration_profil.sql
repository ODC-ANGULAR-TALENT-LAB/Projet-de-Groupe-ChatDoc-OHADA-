-- Profil utilisateur et préférences.
--
-- TROIS BESOINS, TROIS FORMES DIFFÉRENTES.
--
-- `prenom` est une COLONNE et non une préférence : il entre dans le
-- prompt de l'assistant, il est donc soumis à une validation stricte
-- (voir app/services/profil.py) que du JSON libre ne permettrait pas
-- d'imposer.
--
-- `photo_url` pointe vers Google. On stocke l'URL et non l'image :
-- l'avatar est une décoration, pas une donnée dont dépend le service.
-- S'il ne charge pas — hors ligne, ou lien expiré — l'interface affiche
-- les initiales et rien n'est perdu.
--
-- `preferences` est du JSONB : ce sont des réglages d'affichage et de
-- confort, dont la liste bougera. Une colonne par réglage imposerait
-- une migration à chaque ajout, pour des données que personne
-- n'interroge autrement que par utilisateur.

ALTER TABLE utilisateur
    ADD COLUMN IF NOT EXISTS prenom      VARCHAR(60),
    ADD COLUMN IF NOT EXISTS photo_url   TEXT,
    ADD COLUMN IF NOT EXISTS preferences JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN utilisateur.prenom IS
    'Prénom affiché et utilisé par l''assistant. Validé strictement : '
    'il entre dans le prompt système, où du texte libre ouvrirait une '
    'injection.';

COMMENT ON COLUMN utilisateur.photo_url IS
    'Photo du compte Google. Décorative : l''interface retombe sur les '
    'initiales si elle ne charge pas.';
