"""Shared pytest fixtures: isolated PostgreSQL test database, test
client, authenticated seller.

The suite runs against the same engine the app uses in production
(PostgreSQL), in a dedicated `orderkoi_test` database — dev data is
never touched, and dialect-specific SQL is exercised for real.
"""

import os

# Must be set before the app reads its settings — disables rate
# limiting for the suite (it has its own dedicated unit tests), forces
# the email console backend so fixture signups never attempt a real
# SMTP connection (backend/.env may carry live SMTP credentials), and
# redirects every connection to the throwaway test database (real env
# vars take priority over .env, so no file editing is needed).
os.environ["ENVIRONMENT"] = "test"
os.environ["SMTP_HOST"] = ""
os.environ["PG_DATABASE"] = "orderkoi_test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.models  # noqa: E402,F401 — registers every table on Base.metadata
from app.config import get_settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

settings = get_settings()


def _ensure_test_database() -> None:
    """Create the test database if it doesn't exist yet (fresh
    machines). Needs CREATEDB on the app role — see docs/BACKEND_GUIDE."""
    try:
        probe = create_engine(settings.database_url)
        with probe.connect():
            pass
        probe.dispose()
        return
    except OperationalError:
        pass  # database missing — create it below

    # Connect to the maintenance database and create it once
    base_url, _, _ = settings.database_url.rpartition("/")
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{settings.pg_database}"'))
    admin.dispose()


_ensure_test_database()

engine = create_engine(settings.database_url, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _fresh_login_throttle():
    """Reset the in-memory login throttle around every test — lockout
    state from one test must never influence another."""
    from app import login_throttle

    login_throttle._failures.clear()
    login_throttle._locked_until.clear()
    yield
    login_throttle._failures.clear()
    login_throttle._locked_until.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def seller_payload():
    """Unique per test — every test gets its own fresh account."""
    import uuid

    return {
        "email": f"seller-{uuid.uuid4().hex[:10]}@example.com",
        "password": "secretpass123",
        "store_name": "Test Store",
        "phone": "01712345678",
    }


def verify_account(email: str) -> None:
    """Flip email_verified on an account directly — the test-suite
    equivalent of clicking the verification link.

    Fixture accounts come pre-verified so the rest of the suite can
    log in; the verification flow itself has dedicated tests in
    test_email_verification.py.
    """
    db = TestingSessionLocal()
    try:
        from app.models import Seller

        seller = db.query(Seller).filter(Seller.email == email).first()
        assert seller is not None, f"account {email} must exist before verifying"
        seller.email_verified = True
        db.commit()
    finally:
        db.close()


@pytest.fixture
def seller(client, seller_payload):
    """A registered (and email-verified) seller account."""
    response = client.post("/auth/signup", json=seller_payload)
    assert response.status_code == 201, response.text
    verify_account(seller_payload["email"])
    return response.json()


@pytest.fixture
def auth_headers(client, seller, seller_payload):
    """Authorization header for the registered seller."""
    response = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def order_payload():
    return {
        "customer_name": "Rahim Uddin",
        "customer_phone": "01812345678",
        "customer_address": "House 12, Road 5, Dhaka",
        "items": [
            {"name": "Cotton T-Shirt", "quantity": 2, "price": 550},
            {"name": "Cap", "quantity": 1, "price": 300},
        ],
        "notes": "Deliver after 5pm",
    }


@pytest.fixture
def order(client, auth_headers, order_payload):
    """One order owned by the authenticated seller."""
    response = client.post("/orders", json=order_payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


# ---------- Admin fixtures (shared across test modules) ----------

def promote_to_admin(email: str) -> None:
    db = TestingSessionLocal()
    try:
        from app.models import Seller

        seller = db.query(Seller).filter(Seller.email == email).first()
        assert seller is not None, f"account {email} must exist before promoting"
        seller.role = "admin"
        seller.plan = "pro"
        db.commit()
    finally:
        db.close()


@pytest.fixture
def admin_payload():
    import uuid

    return {
        "email": f"admin-{uuid.uuid4().hex[:10]}@example.com",
        "password": "adminpass12345",
        "store_name": "OrderKoi Platform",
    }


@pytest.fixture
def admin_headers(client, admin_payload):
    """A dedicated platform-admin account (separate from any seller)."""
    signup = client.post("/auth/signup", json=admin_payload)
    assert signup.status_code == 201
    verify_account(admin_payload["email"])
    promote_to_admin(admin_payload["email"])

    login = client.post(
        "/auth/login",
        json={"email": admin_payload["email"], "password": admin_payload["password"]},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
