-- Favoris et annotations personnelles (§5, « Should »).
--
-- DEUX BESOINS, UNE SEULE TABLE. Le cahier des charges les cite
-- ensemble — « favoris et annotations personnelles » — et c'est le meme
-- geste : un professionnel marque un article parce qu'il compte pour
-- lui, et note POURQUOI. Deux tables separees obligeraient a inventer
-- une annotation sans favori, qui n'a pas de sens ici.
--
-- CE QUE CETTE TABLE REND POSSIBLE EN PLUS. La veille ciblee : « notifier
-- les utilisateurs ayant consulte ou mis en favori un article modifie ».
-- Sans elle, le journal des mises a jour ne peut s'adresser qu'a tout le
-- monde, c'est-a-dire a personne en particulier.

CREATE TABLE IF NOT EXISTS favori (
    utilisateur_id INT NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    article_id     INT NOT NULL REFERENCES article(id) ON DELETE CASCADE,

    -- L'annotation. Facultative : marquer sans commenter est le cas le
    -- plus frequent, et exiger une note ferait renoncer au favori.
    note           TEXT,

    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le     TIMESTAMPTZ,

    -- LA VERSION VUE AU MOMENT DE LA MISE EN FAVORI. C'est elle qui
    -- permet de dire « l'article que vous suivez a change depuis » :
    -- sans ce repere, on ne saurait comparer a quoi que ce soit, et la
    -- notification ciblee se reduirait a « quelque chose a bouge ».
    version_vue    VARCHAR(50),

    -- Un article ne se met pas deux fois en favori par la meme personne.
    PRIMARY KEY (utilisateur_id, article_id)
);

-- La page « mes favoris » liste par date decroissante : c'est l'ordre
-- dans lequel on retrouve ce qu'on vient de marquer.
CREATE INDEX IF NOT EXISTS idx_favori_utilisateur
    ON favori (utilisateur_id, cree_le DESC);

-- La veille ciblee part de l'ARTICLE et cherche qui le suit — l'index
-- ci-dessus, qui part de l'utilisateur, ne sert a rien pour cela.
CREATE INDEX IF NOT EXISTS idx_favori_article
    ON favori (article_id);
