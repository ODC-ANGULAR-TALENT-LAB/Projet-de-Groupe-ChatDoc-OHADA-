"""Modeles SQLAlchemy - miroir du schema defini dans db/init/01_schema.sql.

Le schema SQL fait autorite : ces classes le refletent, elles ne le
creent pas. Aucune migration automatique n'est declenchee depuis l'API.

REGLE ABSOLUE : aucun UPDATE sur le contenu d'un article. Une
modification legale clot l'ancienne ligne (date_abrogation) et en insere
une nouvelle.
"""

from __future__ import annotations

import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import parametres
from app.db import Base


class Texte(Base):
    """Un texte officiel du corpus (acte uniforme, code)."""

    __tablename__ = "texte"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sigle: Mapped[str] = mapped_column(String(20))
    titre: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(50))
    date_consolidation: Mapped[datetime.date] = mapped_column(Date)
    # Tracabilite : de quoi remonter toute reponse contestee a sa source.
    source_url: Mapped[str | None] = mapped_column(Text)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    valide_par: Mapped[str | None] = mapped_column(String(120))

    articles: Mapped[list[Article]] = relationship(back_populates="texte")


class Article(Base):
    """Unite de decoupage du corpus : la granularite des citations."""

    __tablename__ = "article"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    texte_id: Mapped[int] = mapped_column(ForeignKey("texte.id"))
    numero: Mapped[str] = mapped_column(String(30))
    chemin: Mapped[str] = mapped_column(Text)
    contenu: Mapped[str] = mapped_column(Text)
    date_entree_vigueur: Mapped[datetime.date] = mapped_column(Date)
    # NULL = en vigueur. Une version abrogee n'est jamais supprimee.
    date_abrogation: Mapped[datetime.date | None] = mapped_column(Date)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(parametres.embedding_dimensions)
    )
    recherche_fts: Mapped[str | None] = mapped_column(TSVECTOR)

    texte: Mapped[Texte] = relationship(back_populates="articles")


class Utilisateur(Base):
    """Compte et quota freemium. Le quota est decompte cote serveur.

    Deux moyens de connexion possibles, non exclusifs : un mot de passe
    ou un compte Google. Une contrainte en base impose qu'au moins un
    des deux soit renseigne.
    """

    __tablename__ = "utilisateur"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    # NULL pour un compte cree via Google.
    mot_de_passe_hash: Mapped[str | None] = mapped_column(Text)
    # Claim "sub" du jeton Google : identifiant stable du compte.
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    # 'utilisateur', 'juriste' ou 'admin'. Voir db/05_migration_juriste.sql
    # pour la raison de la distinction entre les deux derniers.
    role: Mapped[str] = mapped_column(String(20), default="utilisateur")
    plan: Mapped[str] = mapped_column(String(20), default="gratuit")
    quota_restant: Mapped[int] = mapped_column(Integer, default=5)
    quota_reinit_le: Mapped[datetime.date | None] = mapped_column(Date)
    # Dernier jour de validite du forfait paye. NULL sur le gratuit.
    # Depassee, le compte retombe sur le gratuit (voir dependances.py).
    plan_echeance: Mapped[datetime.date | None] = mapped_column(Date)

    # ACCEPTATION DES CONDITIONS D'UTILISATION.
    #
    # Deux colonnes et non un booleen : « a accepte » ne prouve rien le
    # jour ou il faudrait le prouver. Accepte QUAND, et accepte QUOI ?
    # Les conditions changent, et celui qui a coche en 2026 n'a pas
    # accepte la version de 2028.
    #
    # NULL pour les comptes anterieurs a la mise en place : on ne leur
    # prete pas un consentement qu'ils n'ont pas donne.
    # PROFIL.
    #
    # `prenom` est une colonne et non une preference : il entre dans le
    # prompt de l'assistant, et subit donc une validation stricte que du
    # JSON libre ne permettrait pas d'imposer (voir services/profil.py).
    prenom: Mapped[str | None] = mapped_column(String(60))
    # Photo du compte Google. DECORATIVE : si elle ne charge pas — hors
    # ligne, lien expire — l'interface affiche les initiales.
    photo_url: Mapped[str | None] = mapped_column(Text)
    # Reglages d'affichage et de confort. En JSONB parce que la liste
    # bougera : une colonne par reglage imposerait une migration a
    # chaque ajout.
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)

    # AVATAR TELEVERSE. Il prime sur `photo_url` : c'est le choix de
    # l'utilisateur, celui de Google n'est qu'un defaut. En base et non
    # sur le disque — l'hebergement vise a un systeme de fichiers
    # ephemere, ou un avatar ecrit disparaitrait au redeploiement.
    photo: Mapped[bytes | None] = mapped_column(LargeBinary)
    photo_type: Mapped[str | None] = mapped_column(String(30))
    # Sert de jeton de cache : l'URL de la photo le porte, si bien qu'un
    # changement se voit tout de suite au lieu d'attendre l'expiration.
    photo_le: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    cgu_version: Mapped[str | None] = mapped_column(String(20))
    cgu_acceptees_le: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    @property
    def est_admin(self) -> bool:
        return self.role == "admin"

    @property
    def est_personnel(self) -> bool:
        """Ce compte sert-il a EXPLOITER le service, ou a s'en servir ?

        UN COMPTE DE PERSONNEL N'EST PAS UN CLIENT. Le juriste depose et
        valide des textes ; l'administrateur tient le service. Ni l'un ni
        l'autre n'achete un forfait, et les compter parmi les abonnes
        fausserait le chiffre d'affaires comme le nombre d'abonnes.

        CONSEQUENCE SUR LE QUOTA : ils en sont exemptes. Un juriste doit
        pouvoir interroger l'assistant autant qu'il le faut pour verifier
        que le texte qu'il vient d'ingerer produit les bonnes citations —
        c'est son travail, pas une consommation. L'arreter a dix
        questions l'empecherait de faire ce pour quoi le compte existe.

        Le cout de cet usage est reel mais borne : ces comptes sont peu
        nombreux et nominatifs, contrairement a un quota ouvert qui
        protege d'inconnus.
        """
        return self.role in ("juriste", "admin")

    @property
    def connexion_google(self) -> bool:
        """Le compte est-il rattache a Google ?

        Sert au diagnostic cote administration : un compte Google n'a
        pas de mot de passe a reinitialiser, et proposer de le faire
        enverrait quelqu'un dans une impasse.
        """
        return self.google_sub is not None

    @property
    def redige_le_corpus(self) -> bool:
        """Peut deposer, analyser et valider un texte du corpus.

        L'administrateur en herite : il serait absurde qu'il ne puisse
        pas depanner un juriste. L'inverse n'est pas vrai — un juriste
        n'attribue pas les roles.
        """
        return self.role in ("juriste", "admin")

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="utilisateur"
    )


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    utilisateur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    titre: Mapped[str | None] = mapped_column(Text)
    cree_le: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    utilisateur: Mapped[Utilisateur] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversation.id"))
    role: Mapped[str] = mapped_column(String(10))
    contenu: Mapped[str] = mapped_column(Text)
    cree_le: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list[Citation]] = relationship(back_populates="message")


class Depot(Base):
    """Un texte televerse, EN ATTENTE DE VALIDATION HUMAINE.

    Rien de ce qui vit ici n'est interrogeable par les utilisateurs. Un
    depot ne devient un texte du corpus qu'apres validation explicite
    d'un administrateur, dont le nom figure ensuite dans la table de
    provenance : valider, c'est engager sa responsabilite.
    """

    __tablename__ = "depot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    depose_par: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))

    nom_fichier: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text)
    sigle: Mapped[str] = mapped_column(String(20))
    titre: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(50))
    date_consolidation: Mapped[datetime.date] = mapped_column(Date)

    statut: Mapped[str] = mapped_column(String(20), default="en_attente")
    articles: Mapped[list] = mapped_column(JSONB)
    problemes: Mapped[list] = mapped_column(JSONB, default=list)

    nb_pages: Mapped[int | None] = mapped_column(Integer)
    extrait_par_ocr: Mapped[bool] = mapped_column(Boolean, default=False)

    # Diff contre le corpus en vigueur + resumes produits par le modele.
    # Fige, comme le decoupage : il faut pouvoir reconstituer apres coup
    # ce qui a ete montre au juriste au moment ou il s'est prononce.
    #
    # La colonne s'appelle `analyse_diff` en base : ANALYSE est un mot
    # reserve de PostgreSQL. L'attribut Python garde le nom lisible.
    analyse: Mapped[list | None] = mapped_column("analyse_diff", JSONB)
    # Numeros retenus quand le juriste ne valide qu'une partie du depot.
    # NULL = tout le depot.
    articles_retenus: Mapped[list | None] = mapped_column(JSONB)

    cree_le: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decide_le: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    decide_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    texte_id: Mapped[int | None] = mapped_column(ForeignKey("texte.id"))


class Citation(Base):
    """Lien entre une reponse et l'article qui la fonde.

    C'est la trace qui rend une reponse verifiable a posteriori, et la
    piece justificative en cas de contestation.
    """

    __tablename__ = "citation"

    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"), primary_key=True)
    extrait: Mapped[str | None] = mapped_column(Text)

    message: Mapped[Message] = relationship(back_populates="citations")
    article: Mapped[Article] = relationship()


class Signalement(Base):
    """Une reponse contestee par un utilisateur.

    LE REGISTRE DES INCIDENTS EST UN DISPOSITIF DE PROTECTION, pas un
    tableau de bord. Le cahier des charges (§16 ter) le range aux cotes
    des conditions d'utilisation et de l'assurance : il demontre la
    diligence de l'editeur en cas de litige.

    Il n'a de valeur que s'il est tenu depuis le debut. Un registre
    ouvert le jour du premier litige ne prouve rien.
    """

    __tablename__ = "signalement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"))
    utilisateur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))

    motif: Mapped[str] = mapped_column(String(30))
    commentaire: Mapped[str | None] = mapped_column(Text)

    statut: Mapped[str] = mapped_column(String(20), default="ouvert")
    correction: Mapped[str | None] = mapped_column(Text)

    cree_le: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    traite_le: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    traite_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))


class Favori(Base):
    """Un article marque par un utilisateur, avec sa note personnelle.

    DEUX BESOINS, UNE SEULE TABLE. Le cahier des charges cite « favoris
    et annotations personnelles » ensemble, et c'est le meme geste : on
    marque un article parce qu'il compte, et on note pourquoi.

    CETTE TABLE EST AUSSI CE QUI REND LA VEILLE CIBLEE POSSIBLE. Sans
    elle, le journal des mises a jour ne peut s'adresser qu'a tout le
    monde — c'est-a-dire a personne en particulier.
    """

    __tablename__ = "favori"

    utilisateur_id: Mapped[int] = mapped_column(
        ForeignKey("utilisateur.id"), primary_key=True
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey("article.id"), primary_key=True
    )

    note: Mapped[str | None] = mapped_column(Text)

    cree_le: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    modifie_le: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # La version du texte telle qu'elle etait au moment du marquage.
    # C'est le repere qui permet de dire « l'article que vous suivez a
    # change depuis » ; sans lui, la notification se reduirait a
    # « quelque chose a bouge ».
    version_vue: Mapped[str | None] = mapped_column(String(50))

    article: Mapped[Article] = relationship()
