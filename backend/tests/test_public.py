"""Public order form tests.

Covers: store lookup by slug, order submission without auth,
seller notification email, validation, and the (removed) plan cap.
"""

import pytest


@pytest.fixture
def captured_email(monkeypatch):
    """Capture emails instead of sending them; expose (to, subject, body)."""
    sent = []

    def fake_send(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr("app.routes.public.send_email", fake_send)
    return sent


@pytest.fixture
def form_payload():
    return {
        "customer_name": "Rahim Uddin",
        "customer_phone": "01812345678",
        "customer_email": "rahim.uddin@example.com",
        "customer_address": "House 12, Road 5, Dhanmondi, Dhaka",
        "items": [
            {"name": "Cotton Panjabi", "quantity": 2, "price": 1200},
            {"name": "Kurta (M)", "quantity": 1, "price": 950},
        ],
        "notes": "Please deliver after 5pm",
    }


# ---------- Pricing / public config ----------

def test_pricing_endpoint_public_and_complete(client):
    """GET /public/stores/pricing needs no auth and carries the whole
    public business config: all three durations priced, the free-plan
    allowance, bKash details and the support contact (all env-driven)."""
    response = client.get("/public/stores/pricing")
    assert response.status_code == 200
    data = response.json()
    assert [e["months"] for e in data["pro"]] == [1, 6, 12]
    for entry in data["pro"]:
        assert isinstance(entry["price"], int)
        assert entry["price"] > 0
    assert isinstance(data["free_plan_orders"], int)
    assert data["free_plan_orders"] > 0
    assert data["bkash_number"]
    assert data["bkash_type"]
    assert "@" in data["support_email"]


def test_pricing_reflects_env_overrides(client, monkeypatch):
    """Config values come from settings — an env change flows through
    the endpoint (this is the 'change one thing in env' contract)."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PRO_PRICE_1M", "299")
    monkeypatch.setenv("PRO_PRICE_6M", "1499")
    monkeypatch.setenv("PRO_PRICE_12M", "2499")
    monkeypatch.setenv("FREE_PLAN_ORDERS", "10")
    monkeypatch.setenv("BKASH_NUMBER", "01700000000")
    monkeypatch.setenv("SUPPORT_EMAIL", "support@orderkoi.example")
    try:
        # re-instantiate settings so the env change is picked up
        from app.config import Settings
        monkeypatch.setattr("app.config.get_settings", lambda: Settings())
        monkeypatch.setattr("app.schemas.get_settings", lambda: Settings())
        data = client.get("/public/stores/pricing").json()
        assert {e["months"]: e["price"] for e in data["pro"]} == {1: 299, 6: 1499, 12: 2499}
        assert data["free_plan_orders"] == 10
        assert data["bkash_number"] == "01700000000"
        assert data["support_email"] == "support@orderkoi.example"
    finally:
        get_settings.cache_clear()


# ---------- Honeypot ----------

def test_honeypot_submission_gets_fake_success(client, seller, form_payload, captured_email):
    """A filled honeypot (bot) gets a plausible 201 — but no order is
    created, no emails go out, and the seller's quota is untouched."""
    from conftest import TestingSessionLocal
    from app.models import Order

    slug = seller["store_slug"]
    before = (
        TestingSessionLocal()
        .query(Order)
        .filter(Order.seller_id == seller["id"])
        .count()
    )

    response = client.post(
        f"/public/stores/{slug}/orders",
        json={**form_payload, "website": "http://spam-bot.example"},
    )
    assert response.status_code == 201
    body = response.json()
    # Right response shape — the bot can't tell it was dropped
    assert set(body) == {"order_number", "tracking_code", "store_name"}

    after = (
        TestingSessionLocal()
        .query(Order)
        .filter(Order.seller_id == seller["id"])
        .count()
    )
    assert before == after  # nothing was created
    assert captured_email == []  # nobody was emailed


def test_honeypot_empty_is_a_normal_order(client, seller, form_payload, captured_email):
    """Empty/absent honeypot (a human) creates the order as usual."""
    response = client.post(
        f"/public/stores/{seller['store_slug']}/orders",
        json={**form_payload, "website": ""},
    )
    assert response.status_code == 201
    assert len(captured_email) == 2  # seller + customer notifications


# ---------- Store lookup ----------

def test_signup_assigns_store_slug(client, seller):
    # Every seller gets a form link; later sellers with the same store
    # name get a suffix, so only the prefix is guaranteed
    assert seller["store_slug"].startswith("test-store")


def test_slugs_are_unique_for_same_store_name(client):
    payload = {
        "email": "same-name-a@example.com",
        "password": "secretpass123",
        "store_name": "Duplicate Shop",
    }
    first = client.post("/auth/signup", json=payload).json()

    payload["email"] = "same-name-b@example.com"
    second = client.post("/auth/signup", json=payload).json()

    assert first["store_slug"] == "duplicate-shop"
    assert second["store_slug"] != first["store_slug"]
    assert second["store_slug"].startswith("duplicate-shop")


def test_get_store_returns_name_only(client, seller):
    response = client.get(f"/public/stores/{seller['store_slug']}")
    assert response.status_code == 200
    data = response.json()
    assert data["store_name"] == seller["store_name"]
    assert data["slug"] == seller["store_slug"]
    # A fresh free store is accepting orders
    assert data["is_accepting_orders"] is True
    # The store header must not leak account details
    assert set(data) == {"store_name", "slug", "is_accepting_orders"}


def test_get_store_unknown_slug_404(client):
    response = client.get("/public/stores/no-such-store")
    assert response.status_code == 404


# ---------- Order submission ----------

def test_submit_order_success(client, seller, seller_payload, auth_headers, form_payload, captured_email):
    slug = seller["store_slug"]

    response = client.post(f"/public/stores/{slug}/orders", json=form_payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["order_number"] == 1
    assert data["tracking_code"]
    assert data["store_name"] == seller["store_name"]
    # Response must not leak seller account data
    assert set(data) == {"order_number", "tracking_code", "store_name"}

    # The order shows up in the seller's dashboard, marked as form-sourced
    orders = client.get("/orders", headers=auth_headers)
    assert orders.status_code == 200
    body = orders.json()
    assert body["total"] == 1
    order = body["orders"][0]
    assert order["source"] == "form"
    assert order["status"] == "placed"
    assert order["total_price"] == 3350  # 2*1200 + 950, computed server-side

    # The tracking code works on the public tracking page immediately
    track = client.get(f"/track/{data['tracking_code']}")
    assert track.status_code == 200

    # The seller got their notification, the customer their confirmation
    assert len(captured_email) == 2
    by_recipient = {email["to"]: email for email in captured_email}

    seller_mail = by_recipient[seller_payload["email"]]
    assert "New order" in seller_mail["subject"]

    customer_mail = by_recipient[form_payload["customer_email"]]
    assert "received" in customer_mail["subject"].lower()
    assert data["tracking_code"] in customer_mail["body"]
    assert f"/track/{data['tracking_code']}" in customer_mail["body"]


def test_submit_order_no_auth_required(client, seller, form_payload):
    """No Authorization header anywhere — the whole point of the form."""
    response = client.post(f"/public/stores/{seller['store_slug']}/orders", json=form_payload)
    assert response.status_code == 201


def test_submit_order_email_failure_never_breaks_submission(client, seller, form_payload, monkeypatch):
    """If email sending explodes, the customer's order must still succeed."""

    def broken_send(to, subject, body):
        raise RuntimeError("SMTP is down")

    monkeypatch.setattr("app.routes.public.send_email", broken_send)

    response = client.post(
        f"/public/stores/{seller['store_slug']}/orders", json=form_payload
    )
    assert response.status_code == 201


def test_submit_order_unknown_slug_404(client, form_payload):
    response = client.post("/public/stores/ghost-shop/orders", json=form_payload)
    assert response.status_code == 404


def test_submit_order_validation(client, seller, form_payload):
    slug = seller["store_slug"]

    # Empty items list
    bad = {**form_payload, "items": []}
    assert client.post(f"/public/stores/{slug}/orders", json=bad).status_code == 422

    # Missing address (required on the public form — couriers need it)
    bad = {k: v for k, v in form_payload.items() if k != "customer_address"}
    assert client.post(f"/public/stores/{slug}/orders", json=bad).status_code == 422

    # Missing email (required — future status notifications go there)
    bad = {k: v for k, v in form_payload.items() if k != "customer_email"}
    assert client.post(f"/public/stores/{slug}/orders", json=bad).status_code == 422

    # Malformed email
    bad = {**form_payload, "customer_email": "not-an-email"}
    assert client.post(f"/public/stores/{slug}/orders", json=bad).status_code == 422

    # Nonsense quantity
    bad = {**form_payload, "items": [{"name": "X", "quantity": 0, "price": 10}]}
    assert client.post(f"/public/stores/{slug}/orders", json=bad).status_code == 422


def test_submit_order_isolated_between_stores(client, seller, form_payload, auth_headers):
    """A form order lands only in the target store — slug = destination."""
    other = client.post(
        "/auth/signup",
        json={
            "email": "other-store@example.com",
            "password": "secretpass123",
            "store_name": "Other Store",
        },
    ).json()

    response = client.post(f"/public/stores/{other['store_slug']}/orders", json=form_payload)
    assert response.status_code == 201

    # The first seller sees nothing
    orders = client.get("/orders", headers=auth_headers)
    assert orders.json()["total"] == 0


# ---------- Free-plan allowance (15 one-time, unlimited on Pro) ----------

def test_submit_order_within_free_allowance(client, seller, form_payload):
    """A fresh Free store's form keeps accepting submissions inside the
    one-time allowance — a new seller never notices it."""
    slug = seller["store_slug"]
    for i in range(5):
        response = client.post(f"/public/stores/{slug}/orders", json=form_payload)
        assert response.status_code == 201


def test_submit_order_blocked_after_allowance(client, seller, auth_headers, form_payload):
    """A Free store's form goes quiet for customers once the one-time
    allowance is used up — 402, with a professional message."""
    slug = seller["store_slug"]
    for _ in range(15):
        response = client.post(f"/public/stores/{slug}/orders", json=form_payload)
        assert response.status_code == 201

    blocked = client.post(f"/public/stores/{slug}/orders", json=form_payload)
    assert blocked.status_code == 402
    assert "upgrade" in blocked.json()["detail"].lower()

    # The seller's dashboard creation is gated too (same allowance)
    dashboard = client.post(
        "/orders",
        json={
            "customer_name": "Dashboard Too",
            "customer_phone": "01800000000",
            "items": [{"name": "X", "quantity": 1, "price": 10}],
        },
        headers=auth_headers,
    )
    assert dashboard.status_code == 402

    # The store header now reports the paused state up front — the
    # customer form can show a notice instead of a rejected submission
    store = client.get(f"/public/stores/{slug}").json()
    assert store["is_accepting_orders"] is False
