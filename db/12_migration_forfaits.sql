-- Forfaits payants : échéance de l'abonnement et demandes de changement.
--
-- POURQUOI UNE ÉCHÉANCE. Sans elle, un paiement unique de 5 000 F
-- ouvrirait le forfait pour toujours : le quota se remet à son plafond
-- chaque mois, et rien ne dirait que le mois payé est écoulé. La date
-- d'échéance est ce qui fait retomber le compte sur le forfait gratuit
-- quand l'abonnement n'est pas renouvelé.
--
-- POURQUOI UNE TABLE DE DEMANDES, ET NON UN SIMPLE CHANGEMENT DE PLAN.
-- L'application n'encaisse pas. Le paiement se fait hors ligne — Mobile
-- Money, espèces — et quelqu'un doit constater qu'il est arrivé avant
-- d'ouvrir les crédits. La demande porte cette attente, et garde la
-- trace de qui a validé quoi, avec quelle référence de paiement. Sans
-- cette trace, un litige sur un abonnement ne se tranche pas.
--
-- LA DESCENTE VERS LE GRATUIT NE PASSE PAS PAR ICI. Renoncer à un
-- forfait ne demande l'accord de personne : c'est immédiat, et aucune
-- demande n'est créée.

ALTER TABLE utilisateur
    ADD COLUMN IF NOT EXISTS plan_echeance DATE;

COMMENT ON COLUMN utilisateur.plan_echeance IS
    'Dernier jour de validite du forfait payant. NULL sur le forfait '
    'gratuit. Depassee, le compte retombe sur le gratuit a la '
    'prochaine lecture.';

CREATE TABLE IF NOT EXISTS demande_abonnement (
    id             SERIAL PRIMARY KEY,
    utilisateur_id INTEGER     NOT NULL
                   REFERENCES utilisateur (id) ON DELETE CASCADE,
    forfait_code   VARCHAR(20) NOT NULL,
    statut         VARCHAR(20) NOT NULL DEFAULT 'en_attente'
                   CHECK (statut IN ('en_attente', 'validee', 'refusee')),
    demande_le     TIMESTAMPTZ NOT NULL DEFAULT now(),
    traite_le      TIMESTAMPTZ,
    traite_par     INTEGER REFERENCES utilisateur (id) ON DELETE SET NULL,
    -- Référence du paiement constatée par l'administrateur : identifiant
    -- de transaction Mobile Money, numéro de reçu. Saisie libre parce
    -- qu'elle dépend de l'opérateur, et jamais devinée par l'application.
    reference      VARCHAR(120),
    motif_refus    TEXT
);

-- Une seule demande en attente par compte : la seconde remplacerait la
-- première sans qu'on sache laquelle honorer.
CREATE UNIQUE INDEX IF NOT EXISTS idx_demande_en_attente_unique
    ON demande_abonnement (utilisateur_id)
    WHERE statut = 'en_attente';

CREATE INDEX IF NOT EXISTS idx_demande_a_traiter
    ON demande_abonnement (demande_le)
    WHERE statut = 'en_attente';

COMMENT ON TABLE demande_abonnement IS
    'Demande de passage a un forfait payant, en attente de constatation '
    'du paiement. L''application n''encaisse pas : elle enregistre la '
    'demande et garde la trace de sa validation.';
