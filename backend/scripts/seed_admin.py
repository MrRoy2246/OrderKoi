"""Create a dedicated platform-admin account (not a shop).

Usage (from backend/):
    python -m scripts.seed_admin admin@yourdomain.com            # random password printed
    python -m scripts.seed_admin admin@yourdomain.com MyPassword # explicit password

Use this on a fresh install for the platform owner. Admins log into
the admin panel; they have no store, no orders, and no seller dashboard.
"""

import secrets
import sys

from app.database import SessionLocal
from app.models import Seller
from app.security import hash_password
from app.slugs import unique_store_slug


def run(email: str, password: str | None) -> None:
    email = email.strip().lower()
    password = password or secrets.token_urlsafe(12)

    db = SessionLocal()
    try:
        existing = db.query(Seller).filter(Seller.email == email).first()
        if existing is not None:
            print(f"An account with email {email!r} already exists.")
            sys.exit(1)

        admin = Seller(
            email=email,
            store_name="OrderKoi Platform",  # cosmetic only — admins have no shop
            store_slug=unique_store_slug(db, "OrderKoi Platform"),
            hashed_password=hash_password(password),
            role="admin",
            plan="pro",
        )
        db.add(admin)
        db.commit()
        print(f"Admin account created: {email}")
        if password:
            print(f"Password: {password}")
        print("Keep these credentials safe — this account manages your whole platform.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python -m scripts.seed_admin <email> [password]")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
