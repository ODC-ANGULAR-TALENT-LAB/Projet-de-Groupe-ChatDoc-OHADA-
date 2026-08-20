-- Paiement Mobile Money rattaché à la demande d'abonnement.
--
-- CE QUI EST STOCKÉ, ET CE QUI NE L'EST PAS. On garde la référence
-- CamPay, le numéro qui a payé et l'opérateur : c'est ce avec quoi un
-- litige se tranche. On ne garde AUCUN secret de paiement, parce que
-- l'application n'en reçoit aucun — le code est saisi par l'abonné sur
-- son propre téléphone, auprès de son opérateur.
--
-- POURQUOI UNE CONTRAINTE D'UNICITÉ SUR LA RÉFÉRENCE. Le paiement est
-- confirmé par deux chemins qui peuvent arriver ensemble : le rappel
-- signé de CamPay, et la vérification que fait le navigateur en
-- attendant. Sans unicité, une transaction pourrait ouvrir deux
-- abonnements. Avec elle, la seconde écriture échoue et l'activation
-- reste idempotente.

ALTER TABLE demande_abonnement
    ADD COLUMN IF NOT EXISTS campay_reference    VARCHAR(80),
    ADD COLUMN IF NOT EXISTS telephone           VARCHAR(20),
    ADD COLUMN IF NOT EXISTS operateur           VARCHAR(30),
    ADD COLUMN IF NOT EXISTS reference_operateur VARCHAR(120),
    ADD COLUMN IF NOT EXISTS paiement_statut     VARCHAR(20);

CREATE UNIQUE INDEX IF NOT EXISTS idx_demande_campay_reference
    ON demande_abonnement (campay_reference)
    WHERE campay_reference IS NOT NULL;

COMMENT ON COLUMN demande_abonnement.campay_reference IS
    'Reference de la transaction CamPay. Unique : elle empeche qu''un '
    'meme paiement ouvre deux abonnements, le rappel signe et la '
    'verification du navigateur pouvant arriver ensemble.';

COMMENT ON COLUMN demande_abonnement.telephone IS
    'Numero Mobile Money ayant paye, au format 237XXXXXXXXX. Ce n''est '
    'pas un secret mais un identifiant : il sert a trancher un litige.';

COMMENT ON COLUMN demande_abonnement.paiement_statut IS
    'Dernier etat connu cote CamPay : PENDING, SUCCESSFUL ou FAILED. '
    'NULL pour une demande reglee hors ligne (especes).';
