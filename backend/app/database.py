"""Database engine, session factory, and base model class."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

is_sqlite = settings.database_url.startswith("sqlite")
is_postgres = settings.database_url.startswith("postgresql")


def _engine_kwargs() -> dict:
    """Dialect-specific engine configuration."""
    if is_sqlite:
        # SQLite needs check_same_thread=False because FastAPI may use
        # different threads for requests sharing one engine.
        return {"connect_args": {"check_same_thread": False}}
    if is_postgres:
        return {
            # Recycle stale connections behind long-lived servers and
            # verify each one before use — survives Postgres restarts.
            "pool_pre_ping": True,
            "pool_size": 5,
            "max_overflow": 10,
            # The app stores/compares naive-UTC datetimes everywhere
            # (day boundaries, token expiry). Postgres interprets a
            # naive parameter in the session timezone, so pin it to
            # UTC — otherwise a server in another zone shifts every
            # boundary comparison.
            "connect_args": {"options": "-c TimeZone=UTC"},
        }
    return {}


engine = create_engine(settings.database_url, **_engine_kwargs())

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
