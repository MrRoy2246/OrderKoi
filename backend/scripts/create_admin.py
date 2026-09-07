"""Create or promote the platform-admin account (superadmin).

One command for every situation:

    # Fresh install / production bootstrap - creates the admin with a
    # random password (printed once) and login-ready email verification
    python -m scripts.create_admin admin@yourdomain.com

    # Same, but with an explicit password (CI, docker bootstrap)
    python -m scripts.create_admin admin@yourdomain.com 'MyStrongPassword'

    # Existing account (e.g. your dev account) becomes the admin
    python -m scripts.create_admin abin@test.com

Idempotent: if the account exists and is already an admin, nothing
changes and the script exits 0 - safe to run in deploy pipelines.

Admins are platform accounts: they get the admin panel, no shop, no
orders. The account is created email-verified on purpose - the script
is run by the platform owner, and a seeded admin with a pending
verification email (which this script never sends) would be locked
out of the login gate.

Usage (from backend/ - connection settings come from .env):
    python -m scripts.create_admin <email> [password]
"""

import secrets
import sys

from sqlalchemy import func
from sqlalchemy.exc import ProgrammingError

from app.database import SessionLocal
from app.models import Seller
from app.security import hash_password
from app.slugs import unique_store_slug

MIN_PASSWORD_LENGTH = 12


def _ensure_admin(db, email: str, password: str | None) -> None:
    try:
        existing = (
            db.query(Seller).filter(func.lower(Seller.email) == email).first()
        )
    except ProgrammingError as exc:
        if "does not exist" in str(exc.orig):
            sys.exit(
                "Database has no schema yet.\n"
                "Run the migrations first:  alembic upgrade head\n"
                "Then re-run:  python -m scripts.create_admin <email>"
            )
        raise

    if existing is not None:
        if existing.role == "admin":
            print(f"{email} is already an admin - nothing to do.")
            return

        # Promote an existing account (their password stays as-is)
        existing.role = "admin"
        existing.plan = "pro"  # the platform owner gets everything
        existing.email_verified = True
        db.commit()
        print(f"Promoted existing account {email} to admin (role=admin, plan=pro).")
        print("Their existing password still works.")
        return

    # Fresh admin account
    password = password or secrets.token_urlsafe(16)
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters - "
            "a platform-admin account is the keys to everything."
        )

    admin = Seller(
        email=email,
        store_name="OrderKoi Platform",  # cosmetic only - admins have no shop
        store_slug=unique_store_slug(db, "OrderKoi Platform"),
        hashed_password=hash_password(password),
        role="admin",
        plan="pro",
        email_verified=True,  # login-ready: see module docstring
    )
    db.add(admin)
    db.commit()

    print(f"Admin account created: {email}")
    if password:
        print(f"Password: {password}")
    print("Log in at /login - this account manages the whole platform.")
    print("Keep these credentials safe (password-manager them now).")


def run(email: str, password: str | None) -> None:
    email = email.strip().lower()
    db = SessionLocal()
    try:
        _ensure_admin(db, email, password)
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python -m scripts.create_admin <email> [password]")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
