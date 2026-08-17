-- Acceptation des conditions générales d'utilisation.
--
-- POURQUOI DEUX COLONNES ET PAS UN BOOLÉEN. Un simple « a accepté »
-- ne prouve rien le jour où il faudrait le prouver : accepté QUAND, et
-- accepté QUOI ? Les conditions changent ; celui qui a coché en 2026
-- n'a pas accepté la version de 2028.
--
-- CE N'EST PAS UNE PRÉCAUTION THÉORIQUE POUR CE PRODUIT. Le cahier des
-- charges (§3, §16 ter) fait de l'avertissement déontologique une
-- obligation : l'outil est une aide documentaire, pas une consultation
-- juridique. Si un utilisateur soutient un jour qu'il l'a pris pour un
-- conseil, la seule réponse solide est la date et la version des
-- conditions qu'il a acceptées.

ALTER TABLE utilisateur
    ADD COLUMN IF NOT EXISTS cgu_version       VARCHAR(20),
    ADD COLUMN IF NOT EXISTS cgu_acceptees_le  TIMESTAMPTZ;

-- Les comptes créés avant cette migration n'ont rien accepté : on les
-- laisse à NULL plutôt que de leur prêter un consentement qu'ils n'ont
-- pas donné. Inscrire une date fausse serait pire que l'absence.
COMMENT ON COLUMN utilisateur.cgu_version IS
    'Version des CGU acceptée à l''inscription. NULL = compte antérieur '
    'à la mise en place, aucun consentement enregistré.';
