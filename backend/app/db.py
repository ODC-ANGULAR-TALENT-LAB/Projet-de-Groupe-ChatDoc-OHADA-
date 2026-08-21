"""Connexion a PostgreSQL.

Une seule base pour le corpus et l'applicatif (document d'architecture,
section 4).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import parametres

# POOL_PRE_PING : on verifie qu'une connexion du pool est encore vivante
# avant de s'en servir. Indispensable en developpement, ou la base
# tourne dans Docker et peut redemarrer — et plus encore avec un
# hebergeur serverless comme Neon, qui SUSPEND la base apres une periode
# d'inactivite. Sans ce controle, la premiere requete apres une veille
# echoue sur une connexion morte, et l'utilisateur voit une erreur pour
# une base parfaitement saine.
#
# POOL_RECYCLE : une connexion inactive au-dela de cinq minutes est
# jetee plutot que reutilisee. Neon et les intermediaires reseau ferment
# les connexions oisives de leur cote ; les recycler avant eux evite de
# decouvrir la coupure au moment d'une requete.
moteur = create_engine(
    parametres.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
)

FabriqueSession = sessionmaker(bind=moteur, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Classe de base des modeles SQLAlchemy (remplie en phase B)."""


def get_db() -> Generator[Session, None, None]:
    """Dependance FastAPI : ouvre une session et la referme toujours."""
    session = FabriqueSession()
    try:
        yield session
    finally:
        session.close()
