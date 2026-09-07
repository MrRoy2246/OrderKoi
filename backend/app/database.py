"""Database engine, session factory, and base model class (PostgreSQL)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# Connection pooling for a long-lived server: pool_pre_ping verifies
# each connection before use (survives Postgres restarts), and a small
# pool + overflow covers concurrent dashboard/order traffic.
#
# The session timezone is pinned to UTC: every timestamp boundary the
# app computes is UTC, and a server configured for another zone must
# never shift how parameters and comparisons are interpreted.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
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
