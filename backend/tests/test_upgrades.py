"""Upgrade request & Pro duration tests.

Real-world flow: seller pays via bKash, submits a request with
the transaction ID, admin verifies and approves — Pro activates for
the paid-for months. Renewals stack; expiry is enforced.
"""

from datetime import timedelta

import pytest

from conftest import TestingSessionLocal


@pytest.fixture
def captured_email(monkeypatch):
    sent = []

    def fake_send(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr("app.routes.auth.send_email", fake_send)
    monkeypatch.setattr("app.routes.admin.send_email", fake_send)
    return sent


# ---------- Seller side ----------

def test_seller_requests_upgrade(client, auth_headers, captured_email):
    response = client.post(
        "/auth/upgrade-requests",
        json={"months": 6, "payment_reference": "BKASH-8H2K9A"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["months"] == 6
    assert data["status"] == "pending"
    assert data["payment_reference"] == "BKASH-8H2K9A"


def test_duplicate_pending_request_rejected(client, auth_headers):
    first = client.post("/auth/upgrade-requests", json={"months": 1}, headers=auth_headers)
    assert first.status_code == 201

    second = client.post("/auth/upgrade-requests", json={"months": 12}, headers=auth_headers)
    assert second.status_code == 409


def test_invalid_duration_rejected(client, auth_headers):
    response = client.post(
        "/auth/upgrade-requests", json={"months": 3}, headers=auth_headers
    )
    assert response.status_code == 422


def test_upgrade_request_history(client, auth_headers):
    request = client.post("/auth/upgrade-requests", json={"months": 1}, headers=auth_headers).json()

    history = client.get("/auth/upgrade-requests", headers=auth_headers)
    assert history.status_code == 200
    entries = history.json()
    assert len(entries) == 1
    assert entries[0]["id"] == request["id"]
    assert entries[0]["status"] == "pending"


# ---------- Admin side ----------

def test_admin_approves_request_activates_pro(client, seller, auth_headers, admin_headers, captured_email):
    # Seller asks for 6 months
    request = client.post(
        "/auth/upgrade-requests",
        json={"months": 6, "payment_reference": "BKASH-XYZ"},
        headers=auth_headers,
    ).json()

    # Admin sees it in the queue
    queue = client.get("/admin/upgrade-requests", headers=admin_headers).json()
    entry = next(r for r in queue if r["id"] == request["id"])
    assert entry["store_name"] == seller["store_name"]
    assert entry["status"] == "pending"

    # Admin approves
    approve = client.patch(
        f"/admin/upgrade-requests/{request['id']}",
        json={"action": "approve"},
        headers=admin_headers,
    )
    assert approve.status_code == 200, approve.text
    result = approve.json()
    assert result["status"] == "approved"
    assert result["plan"] == "pro"
    assert result["plan_expires_at"] is not None

    # The seller's account reflects it immediately
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["plan"] == "pro"

    # Expiry is ~6 months out
    from datetime import datetime

    from app.models import utcnow

    expires = datetime.fromisoformat(me["plan_expires_at"])
    assert expires > utcnow() + timedelta(days=5 * 30)

    # The seller was notified
    assert any("Pro plan is active" in e["subject"] for e in captured_email)


def test_admin_rejects_request(client, auth_headers, admin_headers, captured_email):
    request = client.post("/auth/upgrade-requests", json={"months": 1}, headers=auth_headers).json()

    response = client.patch(
        f"/admin/upgrade-requests/{request['id']}",
        json={"action": "reject"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["granted_until"] is None  # nothing was granted

    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["plan"] == "free"

    # The seller was told
    assert any("not approved" in e["subject"] for e in captured_email)


def test_approved_request_snapshots_its_granted_expiry(client, seller, auth_headers, admin_headers):
    """Each approved request remembers its own outcome — a later renewal
    changes the seller's current expiry but must never rewrite the
    'Pro until' of earlier rows."""
    first = client.post("/auth/upgrade-requests", json={"months": 1}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{first['id']}", json={"action": "approve"}, headers=admin_headers
    )

    # A renewal while Pro is active — stacks on the remaining time
    second = client.post("/auth/upgrade-requests", json={"months": 12}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{second['id']}", json={"action": "approve"}, headers=admin_headers
    )

    queue = client.get("/admin/upgrade-requests", headers=admin_headers).json()
    first_row = next(r for r in queue if r["id"] == first["id"])
    second_row = next(r for r in queue if r["id"] == second["id"])

    assert first_row["granted_until"] is not None
    assert second_row["granted_until"] is not None
    # The renewal produced a later expiry, and the first row still
    # shows its own earlier outcome — not the seller's current one
    assert second_row["granted_until"] > first_row["granted_until"]
    assert first_row["granted_until"] != second_row["plan_expires_at"]
    # The latest grant is what the seller's account now shows
    assert second_row["granted_until"] == second_row["plan_expires_at"]


def test_already_handled_request_409(client, auth_headers, admin_headers):
    request = client.post("/auth/upgrade-requests", json={"months": 1}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{request['id']}",
        json={"action": "approve"},
        headers=admin_headers,
    )

    again = client.patch(
        f"/admin/upgrade-requests/{request['id']}",
        json={"action": "reject"},
        headers=admin_headers,
    )
    assert again.status_code == 409


def test_upgrade_requests_admin_only(client, auth_headers):
    assert client.get("/admin/upgrade-requests", headers=auth_headers).status_code == 403
    assert client.get("/admin/upgrade-requests").status_code == 401
    assert (
        client.patch(
            "/admin/upgrade-requests/1", json={"action": "approve"}, headers=auth_headers
        ).status_code
        == 403
    )


def test_renewal_stacks_on_active_subscription(client, seller, auth_headers, admin_headers):
    """Approving again extends from the current expiry, not from today."""
    from app.models import Seller, utcnow

    first = client.post("/auth/upgrade-requests", json={"months": 12}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{first['id']}", json={"action": "approve"}, headers=admin_headers
    )
    expiry_after_year = client.get("/auth/me", headers=auth_headers).json()["plan_expires_at"]

    # Request one more month a moment later
    second = client.post("/auth/upgrade-requests", json={"months": 1}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{second['id']}", json={"action": "approve"}, headers=admin_headers
    )
    expiry_after_renewal = client.get("/auth/me", headers=auth_headers).json()["plan_expires_at"]

    def parse(value):
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    added = parse(expiry_after_renewal) - parse(expiry_after_year)
    # ~1 month added (27–35 days tolerance), not a reset to today + 1 month
    assert timedelta(days=27) < added < timedelta(days=35)


def test_expired_pro_back_on_free_with_allowance(client, auth_headers):
    """Pro with a past expiry date is effectively Free again — and Free
    carries the one-time allowance, so order 16 is held."""
    from datetime import datetime, timezone

    from app.models import Seller
    from conftest import TestingSessionLocal

    # Fill most of the allowance while Pro is still 'active'
    payload = {
        "customer_name": "Bulk",
        "customer_phone": "01800000000",
        "items": [{"name": "X", "quantity": 1, "price": 10}],
    }
    for i in range(14):
        client.post("/orders", json={**payload, "customer_name": f"Bulk {i}"}, headers=auth_headers)

    db = TestingSessionLocal()
    try:
        me = client.get("/auth/me", headers=auth_headers).json()
        db.query(Seller).filter(Seller.id == me["id"]).update(
            {
                "plan": "pro",
                "plan_expires_at": datetime.now(timezone.utc) - timedelta(days=1),
            }
        )
        db.commit()
    finally:
        db.close()

    # Expired Pro = Free with its one-time 15-order allowance:
    # 15th order accepted, 16th held
    response = client.post("/orders", json=payload, headers=auth_headers)
    assert response.status_code == 201
    blocked = client.post("/orders", json=payload, headers=auth_headers)
    assert blocked.status_code == 402
    summary = client.get("/orders/stats/summary", headers=auth_headers).json()
    assert summary["plan_limit"] == 15


# ---------- Cancellation ----------

def test_seller_cancels_subscription(client, seller, auth_headers, admin_headers, captured_email):
    # Get Pro first (the normal route)
    request = client.post("/auth/upgrade-requests", json={"months": 6}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{request['id']}", json={"action": "approve"}, headers=admin_headers
    )
    assert client.get("/auth/me", headers=auth_headers).json()["plan"] == "pro"

    # Cancel any time
    response = client.post("/auth/cancel-subscription", headers=auth_headers)
    assert response.status_code == 200
    me = response.json()
    assert me["plan"] == "free"
    assert me["plan_expires_at"] is None

    # Admins were notified (business signal)
    assert any("cancelled" in e["subject"].lower() for e in captured_email)


def test_cancel_without_pro_fails(client, auth_headers):
    response = client.post("/auth/cancel-subscription", headers=auth_headers)
    assert response.status_code == 409
    assert "nothing to cancel" in response.json()["detail"]


def test_cancel_requires_authentication(client):
    assert client.post("/auth/cancel-subscription").status_code == 401


# ---------- Subscription ledger ----------

def get_events(client, admin_headers, seller_id):
    events = client.get("/admin/subscription-events", headers=admin_headers).json()
    return [e for e in events if e["seller_id"] == seller_id]


def test_seller_sees_own_history_in_settings(client, seller, auth_headers, admin_headers):
    """Cancellations (and activations/renewals) surface in the seller's
    own Settings history — not just the admin ledger. Each approved
    request carries its request_id so the frontend can show the
    approval and its activation as ONE row, not two."""
    # Subscribe, renew, then cancel — the full lifecycle
    first = client.post("/auth/upgrade-requests", json={"months": 6}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{first['id']}", json={"action": "approve"}, headers=admin_headers
    )
    second = client.post("/auth/upgrade-requests", json={"months": 1}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{second['id']}", json={"action": "approve"}, headers=admin_headers
    )
    client.post("/auth/cancel-subscription", headers=auth_headers)

    history = client.get("/auth/subscription-history", headers=auth_headers)
    assert history.status_code == 200
    events = history.json()
    # Newest first: cancelled, renewed, subscribed
    assert [e["event"] for e in events] == ["cancelled", "renewed", "subscribed"]
    assert events[0]["note"] == "cancelled by seller"
    assert events[1]["months"] == 1
    # The activation/renewal events link back to their requests
    assert events[1]["request_id"] == second["id"]
    assert events[2]["request_id"] == first["id"]
    # A cancellation has no request behind it
    assert events[0]["request_id"] is None
    # The seller view mirrors the admin ledger for their own account
    admin_view = get_events(client, admin_headers, seller["id"])
    assert [e["event"] for e in admin_view] == [e["event"] for e in events]


def test_subscription_history_scoped_to_self(client, auth_headers):
    """A seller's history shows only their own events — another seller's
    activity never leaks in."""
    # This seller submits a request (only creates an UpgradeRequest —
    # no subscription event yet)
    client.post("/auth/upgrade-requests", json={"months": 1}, headers=auth_headers)

    from conftest import verify_account

    other = client.post(
        "/auth/signup",
        json={
            "email": "history-other@example.com",
            "password": "secretpass123",
            "store_name": "History Other",
        },
    ).json()
    verify_account("history-other@example.com")
    login = client.post(
        "/auth/login",
        json={"email": "history-other@example.com", "password": "secretpass123"},
    ).json()
    other_headers = {"Authorization": f"Bearer {login['access_token']}"}

    # The other seller sees nothing — the first seller's activity
    # belongs to the first seller
    events = client.get("/auth/subscription-history", headers=other_headers).json()
    assert events == []


def test_subscription_history_requires_authentication(client):
    assert client.get("/auth/subscription-history").status_code == 401


def test_ledger_records_full_lifecycle(client, seller, auth_headers, admin_headers):
    """subscribe -> renew -> cancel all leave audit entries."""
    # 1. Subscribe (first approval)
    first = client.post("/auth/upgrade-requests", json={"months": 6}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{first['id']}", json={"action": "approve"}, headers=admin_headers
    )
    events = get_events(client, admin_headers, seller["id"])
    assert events[0]["event"] == "subscribed"
    assert events[0]["months"] == 6
    assert "until" in events[0]["note"]
    assert events[0]["store_name"] == seller["store_name"]

    # 2. Renew (second approval while still active)
    second = client.post("/auth/upgrade-requests", json={"months": 1}, headers=auth_headers).json()
    client.patch(
        f"/admin/upgrade-requests/{second['id']}", json={"action": "approve"}, headers=admin_headers
    )
    events = get_events(client, admin_headers, seller["id"])
    assert events[0]["event"] == "renewed"
    assert events[0]["months"] == 1

    # 3. Cancel by seller
    client.post("/auth/cancel-subscription", headers=auth_headers)
    events = get_events(client, admin_headers, seller["id"])
    assert events[0]["event"] == "cancelled"
    assert events[0]["note"] == "cancelled by seller"
    # Newest first: cancelled, renewed, subscribed
    assert [e["event"] for e in events] == ["cancelled", "renewed", "subscribed"]


def test_ledger_records_manual_admin_changes(client, seller, auth_headers, admin_headers):
    api_set_plan = client.patch(
        f"/admin/sellers/{seller['id']}/plan", json={"plan": "pro"}, headers=admin_headers
    )
    assert api_set_plan.status_code == 200
    events = get_events(client, admin_headers, seller["id"])
    assert events[0]["event"] == "subscribed"
    assert "manually" in events[0]["note"]

    client.patch(
        f"/admin/sellers/{seller['id']}/plan", json={"plan": "free"}, headers=admin_headers
    )
    events = get_events(client, admin_headers, seller["id"])
    assert events[0]["event"] == "cancelled"
    assert "manually" in events[0]["note"]


def test_ledger_admin_only(client, auth_headers):
    assert client.get("/admin/subscription-events", headers=auth_headers).status_code == 403
    assert client.get("/admin/subscription-events").status_code == 401


# ---------- Dashboard stats ranges ----------

def test_stats_range_filters(client, auth_headers, order):
    # The conftest order was created now — visible in every window
    today = client.get("/orders/stats/summary?range=today", headers=auth_headers).json()
    assert today["range"] == "today"
    assert today["total_orders"] == 1
    assert today["revenue"] == 1400
    assert len(today["daily"]) == 1

    week = client.get("/orders/stats/summary?range=7d", headers=auth_headers).json()
    assert week["total_orders"] == 1
    assert len(week["daily"]) == 7

    month = client.get("/orders/stats/summary?range=30d", headers=auth_headers).json()
    assert len(month["daily"]) == 30

    everything = client.get("/orders/stats/summary?range=all", headers=auth_headers).json()
    assert everything["total_orders"] == 1

    # Pending is the current workload, independent of range
    assert today["pending_orders"] == 1


def test_stats_range_invalid_value(client, auth_headers):
    response = client.get("/orders/stats/summary?range=yearly", headers=auth_headers)
    assert response.status_code == 422


def test_stats_custom_range(client, auth_headers, order):
    from datetime import timedelta

    from app.timezone import business_today

    today = business_today()
    start = (today - timedelta(days=6)).isoformat()
    end = today.isoformat()

    stats = client.get(
        f"/orders/stats/summary?range=custom&start={start}&end={end}",
        headers=auth_headers,
    )
    assert stats.status_code == 200
    body = stats.json()
    assert body["range"] == "custom"
    assert body["total_orders"] == 1  # created moments ago — inside the window
    assert len(body["daily"]) == 7

    # A window that ends yesterday excludes today's order
    past_end = (today - timedelta(days=1)).isoformat()
    stats = client.get(
        f"/orders/stats/summary?range=custom&start={start}&end={past_end}",
        headers=auth_headers,
    )
    assert stats.json()["total_orders"] == 0

    # Single-day window works (start == end)
    stats = client.get(
        f"/orders/stats/summary?range=custom&start={end}&end={end}",
        headers=auth_headers,
    )
    assert stats.json()["total_orders"] == 1


def test_stats_custom_range_validation(client, auth_headers):
    # Missing dates
    response = client.get("/orders/stats/summary?range=custom", headers=auth_headers)
    assert response.status_code == 422

    # start after end
    response = client.get(
        "/orders/stats/summary?range=custom&start=2026-02-01&end=2026-01-01",
        headers=auth_headers,
    )
    assert response.status_code == 422

    # Span longer than a year
    response = client.get(
        "/orders/stats/summary?range=custom&start=2024-01-01&end=2026-01-01",
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_stats_include_plan_usage_meter(client, auth_headers, order):
    stats = client.get("/orders/stats/summary", headers=auth_headers).json()
    # month_orders is the lifetime usage meter; plan_limit is the Free
    # allowance (None would mean unlimited — that's Pro's answer)
    assert stats["month_orders"] == 1
    assert stats["plan_limit"] == 15


def test_orders_multi_status_filter(client, auth_headers, order):
    # Pending = placed + confirmed in one request
    response = client.get(
        "/orders?status=placed&status=confirmed", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # A filter that excludes 'placed' returns nothing
    response = client.get(
        "/orders?status=delivered&status=cancelled", headers=auth_headers
    )
    assert response.json()["total"] == 0
