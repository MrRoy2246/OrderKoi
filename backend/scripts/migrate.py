"""Lightweight schema migration for the dev SQLite database.

Adds columns introduced after the database was first created
(uvicorn's create_all only creates missing *tables*, never columns).

Usage (from backend/):
    python -m scripts.migrate
"""

from sqlalchemy import inspect, text

from app.database import engine
from app.models import Seller
from app.slugs import unique_store_slug
from app.database import SessionLocal

NEW_COLUMNS = {
    "sellers": {
        "role": "ALTER TABLE sellers ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'seller'",
        "plan": "ALTER TABLE sellers ADD COLUMN plan VARCHAR(20) NOT NULL DEFAULT 'free'",
        "plan_expires_at": "ALTER TABLE sellers ADD COLUMN plan_expires_at DATETIME",
        "store_slug": "ALTER TABLE sellers ADD COLUMN store_slug VARCHAR(120)",
    },
    "orders": {
        "source": "ALTER TABLE orders ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'dashboard'",
        "customer_email": "ALTER TABLE orders ADD COLUMN customer_email VARCHAR(255)",
    },
    "upgrade_requests": {
        "granted_until": "ALTER TABLE upgrade_requests ADD COLUMN granted_until DATETIME",
    },
}


def run() -> None:
    inspector = inspect(engine)

    for table, columns in NEW_COLUMNS.items():
        if table not in inspector.get_table_names():
            print(f"Table {table!r} does not exist yet — nothing to migrate.")
            continue

        existing = {column["name"] for column in inspector.get_columns(table)}
        with engine.begin() as connection:
            for name, statement in columns.items():
                if name not in existing:
                    connection.execute(text(statement))
                    print(f"Added column {table}.{name}")
                else:
                    print(f"Column {table}.{name} already present")

    # Backfill: every seller needs a unique public form slug
    db = SessionLocal()
    try:
        missing = db.query(Seller).filter(Seller.store_slug.is_(None)).all()
        for seller in missing:
            seller.store_slug = unique_store_slug(db, seller.store_name, seller.id)
            print(f"Assigned slug {seller.store_slug!r} to {seller.store_name!r}")
        if missing:
            db.commit()
        else:
            print("All sellers already have a store slug")
    finally:
        db.close()

    # Uniqueness at the DB level for fresh-slug inserts (SQLite ALTER
    # can't add constraints, so an explicit unique index does the job)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_sellers_store_slug ON sellers (store_slug)")
        )
    print("Unique index on sellers.store_slug ensured")

    # P0 audit fix: order numbers must be unique per seller. A race in
    # "max + 1" created duplicates; the index makes the DB refuse them
    # (the API retries with a fresh number — see _insert_order_with_retry).
    with engine.begin() as connection:
        duplicates = connection.execute(
            text(
                "SELECT seller_id, order_number, COUNT(*) FROM orders "
                "GROUP BY seller_id, order_number HAVING COUNT(*) > 1"
            )
        ).fetchall()
        if duplicates:
            print(
                f"WARNING: {len(duplicates)} duplicate order number(s) exist — "
                "resolve them before the unique index can be created."
            )
        else:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_seller_number "
                    "ON orders (seller_id, order_number)"
                )
            )
            print("Unique index on orders (seller_id, order_number) ensured")
    print("Migration complete.")


if __name__ == "__main__":
    run()
