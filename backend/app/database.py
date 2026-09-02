"""Database engine, session factory, and base model class."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# SQLite needs check_same_thread=False because FastAPI may use
# different threads for requests sharing one engine.
is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if is_sqlite else {},
)

if is_sqlite and not settings.database_url.startswith("sqlite://:memory:") and settings.environment != "test":
    # WAL mode: writers don't block readers, and concurrent commits
    # contend far less — meaningful for simultaneous order creation.
    # Skipped for the in-memory test DB (StaticPool single connection).
    @event.listens_for(engine, "connect")
    def _enable_wal(dbapi_connection, _record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

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
