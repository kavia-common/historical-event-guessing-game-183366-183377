import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

# Base class for ORM models
Base = declarative_base()


def _build_database_url_from_env() -> Optional[str]:
    """
    Build a SQLAlchemy DATABASE_URL from POSTGRES_* environment variables
    if DATABASE_URL is not directly provided.
    """
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")

    if all([host, port, db, user, password]):
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return None


def _get_database_url() -> str:
    """
    Resolve the database URL using the following precedence:
    1. DATABASE_URL env var
    2. Construct from POSTGRES_* vars
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    url = _build_database_url_from_env()
    if url:
        return url

    # As a last resort, raise an explicit error to guide configuration.
    raise RuntimeError(
        "DATABASE_URL is not set and POSTGRES_* variables are incomplete. "
        "Please configure database connection via environment variables."
    )


# Initialize SQLAlchemy engine and session factory
DATABASE_URL = _get_database_url()

# The pool_pre_ping ensures dead connections are refreshed
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

# Configure session factory
SessionLocal = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
)


# PUBLIC_INTERFACE
def get_db_session():
    """Provide the scoped session object for advanced usage (e.g., dependency injection)."""
    return SessionLocal


@contextmanager
def session_scope() -> Generator:
    """
    Context manager for a database session.

    Usage:
        with session_scope() as session:
            # use session
            session.add(obj)
            ...
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# PUBLIC_INTERFACE
def init_db():
    """Create all tables declared on the Base metadata. Safe to call at startup."""
    # Import models to register their metadata with Base before create_all
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
