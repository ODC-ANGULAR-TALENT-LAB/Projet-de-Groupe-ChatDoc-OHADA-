-- Photo de profil téléversée par l'utilisateur.
--
-- POURQUOI EN BASE ET NON SUR LE DISQUE. L'API est destinée à un
-- hébergement à système de fichiers éphémère (Railway, Render) : un
-- fichier écrit sur le disque disparaît au redéploiement suivant. Les
-- avatars s'évaporeraient sans que personne comprenne pourquoi.
--
-- Le coût est maîtrisé parce que l'image est redimensionnée avant
-- stockage : 256×256 en WebP, soit une dizaine de kilo-octets. Ce
-- serait un mauvais calcul pour des pièces jointes, c'en est un bon
-- pour un avatar.
--
-- DEUX COLONNES ET NON UNE. `photo_url` reste la photo Google ;
-- `photo` est celle que l'utilisateur a choisie. Les garder séparées
-- permet de revenir à la photo Google en supprimant la sienne, plutôt
-- que de tomber sur les initiales.

ALTER TABLE utilisateur
    ADD COLUMN IF NOT EXISTS photo       BYTEA,
    ADD COLUMN IF NOT EXISTS photo_type  VARCHAR(30),
    ADD COLUMN IF NOT EXISTS photo_le    TIMESTAMPTZ;

COMMENT ON COLUMN utilisateur.photo IS
    'Avatar téléversé, redimensionné en 256x256 WebP. Prime sur '
    'photo_url. NULL = on retombe sur la photo Google, puis sur les '
    'initiales.';

COMMENT ON COLUMN utilisateur.photo_le IS
    'Date du dernier téléversement. Sert de jeton de cache : l''URL de '
    'la photo la porte, si bien qu''un changement d''avatar est vu '
    'immédiatement au lieu d''attendre l''expiration du cache.';
