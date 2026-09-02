"""Shared pytest fixtures: isolated DB, test client, authenticated seller."""

import os

# Must be set before the app reads its settings — disables rate
# limiting for the suite (it has its own dedicated unit tests).
os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# In-memory SQLite shared across the suite via a single connection
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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


@pytest.fixture
def seller(client, seller_payload):
    """A registered seller account."""
    response = client.post("/auth/signup", json=seller_payload)
    assert response.status_code == 201, response.text
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
    promote_to_admin(admin_payload["email"])

    login = client.post(
        "/auth/login",
        json={"email": admin_payload["email"], "password": admin_payload["password"]},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
