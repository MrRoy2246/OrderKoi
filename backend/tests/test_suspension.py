"""Admin seller suspension.

Suspension is enforced in three separate places, and this file covers
each one: login refuses a token, every authenticated route rejects, and
the public order endpoint refuses new business. Missing any one of them
leaves a hole — a token minted before the suspension, or a customer
posting straight to the public endpoint.

The other half of the feature is what suspension must NOT break: a
suspended seller's existing customers still have orders to track, and
undoing a mistake has to be one click.
"""

import pytest

from conftest import TestingSessionLocal


@pytest.fixture
def form_payload():
    """A customer submission for the *public* form.

    Its own fixture rather than conftest's order_payload: the public
    schema additionally requires customer_email and customer_address,
    which the seller's dashboard payload does not carry.
    """
    return {
        "customer_name": "Rahim Uddin",
        "customer_phone": "01812345678",
        "customer_email": "rahim.uddin@example.com",
        "customer_address": "House 12, Road 5, Dhanmondi, Dhaka",
        "items": [{"name": "Cotton Panjabi", "quantity": 2, "price": 1200}],
        "notes": "Please deliver after 5pm",
    }


def suspend(client, admin_headers, seller_id, reason="terms violation"):
    return client.patch(
        f"/admin/sellers/{seller_id}/suspension",
        json={"suspended": True, "reason": reason},
        headers=admin_headers,
    )


def reinstate(client, admin_headers, seller_id):
    return client.patch(
        f"/admin/sellers/{seller_id}/suspension",
        json={"suspended": False},
        headers=admin_headers,
    )


# ---------- the admin action itself ----------

def test_admin_can_suspend_a_seller(client, admin_headers, seller):
    response = suspend(client, admin_headers, seller["id"])
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["suspended_at"] is not None
    assert body["suspended_reason"] == "terms violation"


def test_the_seller_list_reports_suspension(client, admin_headers, seller):
    """The admin directory has to show who is currently cut off —
    otherwise the only way to know is to remember."""
    suspend(client, admin_headers, seller["id"])

    listing = client.get("/admin/sellers", headers=admin_headers).json()
    entry = next(s for s in listing["sellers"] if s["id"] == seller["id"])
    assert entry["suspended_at"] is not None
    assert entry["suspended_reason"] == "terms violation"


def test_admins_cannot_be_suspended(client, admin_headers, admin_payload):
    """Suspending yourself would lock the only person who can undo it
    out of the panel that does the undoing."""
    db = TestingSessionLocal()
    try:
        from app.models import Seller

        admin_id = db.query(Seller).filter(Seller.email == admin_payload["email"]).one().id
    finally:
        db.close()

    response = suspend(client, admin_headers, admin_id)
    assert response.status_code == 409


def test_a_normal_seller_cannot_suspend_anyone(client, auth_headers, seller):
    """Admin-only. A seller must not be able to cut off a competitor."""
    response = client.patch(
        f"/admin/sellers/{seller['id']}/suspension",
        json={"suspended": True},
        headers=auth_headers,
    )
    assert response.status_code == 403


def test_suspending_twice_keeps_the_original_timestamp(client, admin_headers, seller):
    """Idempotent: a double click, or a retry after a timeout, must not
    rewrite when the suspension started."""
    first = suspend(client, admin_headers, seller["id"]).json()["suspended_at"]
    second = suspend(client, admin_headers, seller["id"], reason="second click").json()

    assert second["suspended_at"] == first
    # The reason is the latest one given, though — that is the useful
    # behaviour for an admin correcting their own note.
    assert second["suspended_reason"] == "second click"


def test_suspending_an_unknown_seller_is_404(client, admin_headers):
    response = suspend(client, admin_headers, 999_999)
    assert response.status_code == 404


# ---------- enforcement: login ----------

def test_suspended_seller_cannot_log_in(client, admin_headers, seller, seller_payload):
    suspend(client, admin_headers, seller["id"])

    response = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert response.status_code == 403
    assert "suspended" in response.json()["detail"].lower()


def test_a_wrong_password_still_gets_the_generic_error(client, admin_headers, seller, seller_payload):
    """Suspension must not be disclosed to someone guessing passwords —
    that would turn a banned account into a confirmed account."""
    suspend(client, admin_headers, seller["id"])

    response = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": "definitely-wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


# ---------- enforcement: existing sessions ----------

def test_a_token_minted_before_the_suspension_stops_working(client, admin_headers, seller, auth_headers):
    """The important case: the seller is already signed in. Suspension
    has to take effect without waiting for their token to expire."""
    assert client.get("/orders", headers=auth_headers).status_code == 200

    suspend(client, admin_headers, seller["id"])

    response = client.get("/orders", headers=auth_headers)
    assert response.status_code == 403
    assert "suspended" in response.json()["detail"].lower()


# ---------- enforcement: the public storefront ----------

def test_suspended_store_stops_accepting_public_orders(client, admin_headers, seller, form_payload):
    """The store page is a courtesy; this endpoint is public and can be
    posted to directly, so it has to refuse on its own."""
    before = client.post(f"/public/stores/{seller['store_slug']}/orders", json=form_payload)
    assert before.status_code == 201, before.text

    suspend(client, admin_headers, seller["id"])

    after = client.post(f"/public/stores/{seller['store_slug']}/orders", json=form_payload)
    assert after.status_code == 403
    assert "accepting new orders" in after.json()["detail"].lower()


def test_suspended_store_tells_the_form_it_is_paused(client, admin_headers, seller):
    """So the customer sees the "temporarily paused" card instead of
    filling in a whole form and being rejected at submit."""
    assert client.get(f"/public/stores/{seller['store_slug']}").json()["is_accepting_orders"] is True

    suspend(client, admin_headers, seller["id"])

    body = client.get(f"/public/stores/{seller['store_slug']}").json()
    assert body["is_accepting_orders"] is False
    # The page still renders — the customer needs to be told something,
    # not shown a 404 for a link that worked yesterday.
    assert body["store_name"] == seller["store_name"]


# ---------- what suspension must not break ----------

def test_existing_customers_can_still_track_their_orders(client, admin_headers, seller, order):
    """Orders already placed are real, and their customers did nothing
    wrong. Cutting off the seller must not strand them."""
    suspend(client, admin_headers, seller["id"])

    response = client.get(f"/track/{order['tracking_code']}")
    assert response.status_code == 200, response.text


# ---------- reversibility ----------

def test_reinstating_restores_login_and_api_access(client, admin_headers, seller, seller_payload):
    suspend(client, admin_headers, seller["id"])
    assert client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    ).status_code == 403

    response = reinstate(client, admin_headers, seller["id"])
    assert response.status_code == 200
    assert response.json()["suspended_at"] is None

    login = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert login.status_code == 200, login.text

    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/orders", headers=headers).status_code == 200


def test_reinstating_lets_the_store_take_orders_again(client, admin_headers, seller, form_payload):
    suspend(client, admin_headers, seller["id"])
    assert client.post(
        f"/public/stores/{seller['store_slug']}/orders", json=form_payload
    ).status_code == 403

    reinstate(client, admin_headers, seller["id"])

    response = client.post(f"/public/stores/{seller['store_slug']}/orders", json=form_payload)
    assert response.status_code == 201, response.text


def test_reinstating_keeps_the_sellers_orders(client, admin_headers, seller, auth_headers, order):
    """Nothing is deleted by a suspension, so the data is all still
    there when it is lifted."""
    suspend(client, admin_headers, seller["id"])
    reinstate(client, admin_headers, seller["id"])

    response = client.get("/orders", headers=auth_headers)
    assert response.status_code == 200
    assert any(o["id"] == order["id"] for o in response.json()["orders"])


# ---------- the marker the frontend keys off ----------

def test_the_suspension_403_carries_the_marker_header(
    client, admin_headers, seller, seller_payload, auth_headers
):
    """The frontend tells a suspension apart from every other 403 by
    this header (app/deps.py SUSPENDED_HEADER) rather than by matching
    the message text — so it has to be on both routes that raise it."""
    suspend(client, admin_headers, seller["id"])

    from app.deps import SUSPENDED_HEADER

    on_auth_route = client.get("/orders", headers=auth_headers)
    assert on_auth_route.status_code == 403
    assert on_auth_route.headers.get(SUSPENDED_HEADER) == "1"

    on_login = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert on_login.status_code == 403
    assert on_login.headers.get(SUSPENDED_HEADER) == "1"


def test_an_ordinary_403_does_not_carry_the_marker(client, auth_headers):
    """The counter-case: a seller hitting an admin route gets a plain
    403. If that carried the marker too, the frontend would sign them
    out with "your account is suspended" for clicking a wrong link."""
    from app.deps import SUSPENDED_HEADER

    response = client.get("/admin/sellers", headers=auth_headers)
    assert response.status_code == 403
    assert response.headers.get(SUSPENDED_HEADER) is None


def test_cors_exposes_the_marker_header(client):
    """A custom response header is invisible to browser JS unless CORS
    names it in Access-Control-Expose-Headers. Without this the whole
    client-side check silently never fires — and only in a browser, so
    a missing expose_headers would pass every other test here."""
    from app.config import get_settings
    from app.deps import SUSPENDED_HEADER

    origin = get_settings().cors_origins[0]
    response = client.get("/health", headers={"Origin": origin})

    exposed = response.headers.get("access-control-expose-headers", "")
    assert SUSPENDED_HEADER.lower() in exposed.lower()


# ---------- the admin surfaces that report it ----------

def test_the_shop_detail_stats_report_suspension(client, admin_headers, seller):
    """The drill-down page is reachable by direct URL, so it can't rely
    on the directory endpoint having told it the shop is suspended."""
    before = client.get(f"/admin/sellers/{seller['id']}/stats", headers=admin_headers).json()
    assert before["suspended_at"] is None

    suspend(client, admin_headers, seller["id"])

    after = client.get(f"/admin/sellers/{seller['id']}/stats", headers=admin_headers).json()
    assert after["suspended_at"] is not None
    assert after["suspended_reason"] == "terms violation"
