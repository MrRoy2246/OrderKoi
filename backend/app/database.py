"""Database engine, session factory, and base model class (PostgreSQL)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# Connection pooling for a long-lived server: pool_pre_ping verifies
# each connection before use (survives Postgres restarts), and the pool
# is sized to cover concurrent dashboard/order traffic. The pool size
# and recycle window are settings — size them to your deployment
# (see backend/.env.example) rather than editing this file.
#
# The session timezone is pinned to UTC: every timestamp boundary the
# app computes is UTC, and a server configured for another zone must
# never shift how parameters and comparisons are interpreted.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_timeout=settings.db_pool_timeout_seconds,
    connect_args={"options": "-c TimeZone=UTC"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class all ORM models inherit from."""


def get_db():
    """FastAPI dependency: yields a DB session, always closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
