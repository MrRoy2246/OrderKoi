"""Promote an existing account to platform admin.

Usage (from backend/):
    python -m scripts.make_admin abin@test.com

Run the migration first if the role column is new:
    python -m scripts.migrate
"""

import sys

from app.database import SessionLocal
from app.models import Seller


def run(email: str) -> None:
    email = email.strip().lower()
    db = SessionLocal()
    try:
        seller = db.query(Seller).filter(Seller.email == email).first()
        if seller is None:
            print(f"No account found with email {email!r}.")
            sys.exit(1)

        seller.role = "admin"
        seller.plan = "pro"  # the platform owner gets everything
        db.commit()
        print(f"DONE: {email} is now an admin (role=admin, plan=pro).")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.make_admin <email>")
        sys.exit(1)
    run(sys.argv[1])
