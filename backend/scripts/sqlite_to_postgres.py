"""One-off migration: copy dev data from the legacy SQLite database
into the configured PostgreSQL database (DATABASE_URL / PG_* in .env).

Keeps every row's id (foreign keys and history stay intact) and resets
each table's id sequence afterwards so new inserts don't collide.

Schema must already exist on the target — run `alembic upgrade head`
first. Refuses to run if the target already has sellers (pass --force
to wipe and redo).

Usage (from backend/, with .env pointing at PostgreSQL):
    python -m scripts.sqlite_to_postgres [source.db] [--force]
"""

import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.config import get_settings
from app.database import Base
import app.models  # noqa: F401 — registers every table on Base.metadata

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = BACKEND_DIR / "orderkoi.db"

# Copy order respects foreign keys: sellers first, then everything
# that references them (subscription_events also references
# upgrade_requests, so it goes after that).
TABLES = [
    "sellers",
    "email_verification_tokens",
    "password_reset_tokens",
    "upgrade_requests",
    "subscription_events",
    "orders",
]


def run(source_path: Path, force: bool = False) -> int:
    settings = get_settings()

    if not settings.database_url.startswith("postgresql"):
        print(f"Target DATABASE_URL must be PostgreSQL, got: {settings.database_url}")
        return 1
    if not source_path.exists():
        print(f"Source database not found: {source_path}")
        return 1

    source = create_engine(f"sqlite:///{source_path}")
    target = create_engine(
        settings.database_url,
        connect_args={"options": "-c TimeZone=UTC"},
    )

    # Target must have the schema (alembic) and be empty
    inspector = inspect(target)
    missing = [t for t in TABLES if t not in inspector.get_table_names()]
    if missing:
        print(f"Target is missing tables {missing} — run `alembic upgrade head` first.")
        return 1

    with target.connect() as check:
        existing = check.execute(text("SELECT COUNT(*) FROM sellers")).scalar()
    if existing:
        if not force:
            print(
                f"Target already has {existing} seller(s). "
                "Refusing to mix data — pass --force to wipe and redo."
            )
            return 1
        print(f"--force: wiping {existing} seller row(s) and dependents...")
        with target.begin() as wipe:
            for table in reversed(TABLES):
                wipe.execute(text(f"DELETE FROM {table}"))

    metadata = {t.name: t for t in Base.metadata.sorted_tables}

    with source.connect() as src, target.begin() as txn:
        total = 0
        for table_name in TABLES:
            table = metadata[table_name]
            rows = [dict(row) for row in src.execute(table.select()).mappings()]
            if rows:
                txn.execute(table.insert(), rows)
            print(f"{table_name}: {len(rows)} row(s) copied")
            total += len(rows)

        # New inserts must continue after the copied ids, not collide
        for table_name in TABLES:
            txn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, false)"
                )
            )

    print(f"Done — {total} row(s) migrated. SQLite source left untouched at {source_path}")
    source.dispose()
    target.dispose()
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    source = Path(args[0]) if args else DEFAULT_SOURCE
    raise SystemExit(run(source, force="--force" in sys.argv))
