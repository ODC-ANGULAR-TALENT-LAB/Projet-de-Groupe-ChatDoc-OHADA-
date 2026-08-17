"""Connexion a PostgreSQL.

Une seule base pour le corpus et l'applicatif (document d'architecture,
section 4).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import parametres

# pool_pre_ping : la base tourne dans Docker et peut etre redemarree
# pendant une session de developpement ; on evite les connexions mortes.
moteur = create_engine(parametres.database_url, pool_pre_ping=True)

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
