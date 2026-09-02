"""Orders API tests: CRUD, workflow, ownership, validation."""


def create_order(client, headers, **overrides):
    payload = {
        "customer_name": "Test Customer",
        "customer_phone": "01811111111",
        "items": [{"name": "Item", "quantity": 1, "price": 100}],
    }
    payload.update(overrides)
    return client.post("/orders", json=payload, headers=headers)


def test_create_order(client, auth_headers, order_payload):
    response = client.post("/orders", json=order_payload, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "placed"
    assert body["order_number"] == 1
    # Total computed server-side: 2*550 + 1*300 = 1400
    assert body["total_price"] == 1400
    assert len(body["tracking_code"]) == 8
    assert body["status_history"][0]["status"] == "placed"


def test_create_order_rejects_negative_price(client, auth_headers):
    response = create_order(
        client, auth_headers, items=[{"name": "X", "quantity": 1, "price": -5}]
    )
    assert response.status_code == 422


def test_create_order_rejects_empty_items(client, auth_headers):
    response = create_order(client, auth_headers, items=[])
    assert response.status_code == 422


def test_create_order_rejects_missing_customer(client, auth_headers):
    response = create_order(client, auth_headers, customer_name="")
    assert response.status_code == 422


def test_order_numbers_increment_per_seller(client, auth_headers):
    first = create_order(client, auth_headers).json()
    second = create_order(client, auth_headers).json()
    assert second["order_number"] == first["order_number"] + 1


def test_list_orders(client, auth_headers, order):
    response = client.get("/orders", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["orders"][0]["id"] == order["id"]


def test_search_by_phone_fragment(client, auth_headers):
    create_order(client, auth_headers, customer_phone="01822222222")
    create_order(client, auth_headers, customer_phone="01733333333")
    response = client.get("/orders?q=0182", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["orders"][0]["customer_phone"] == "01822222222"


def test_filter_by_status(client, auth_headers, order):
    response = client.get("/orders?status=placed", headers=auth_headers)
    assert response.json()["total"] == 1
    response = client.get("/orders?status=delivered", headers=auth_headers)
    assert response.json()["total"] == 0


def test_filter_by_date_range(client, auth_headers):
    """start/end are business-timezone calendar days, inclusive."""
    from datetime import timedelta

    from app.timezone import business_today

    create_order(client, auth_headers, customer_name="Range Today")
    create_order(client, auth_headers, customer_name="Range Today 2")
    today = business_today()
    past = today - timedelta(days=30)

    # Window covering today includes both just-created orders
    body = client.get(
        f"/orders?start={today}&end={today}", headers=auth_headers
    ).json()
    assert body["total"] == 2

    # A window entirely in the past excludes them
    body = client.get(
        f"/orders?start={past}&end={past}", headers=auth_headers
    ).json()
    assert body["total"] == 0

    # Open-ended: only a start date
    body = client.get(f"/orders?start={today}", headers=auth_headers).json()
    assert body["total"] == 2
    body = client.get(f"/orders?end={past}", headers=auth_headers).json()
    assert body["total"] == 0

    # start after end is rejected
    response = client.get(
        f"/orders?start={today}&end={past}", headers=auth_headers
    )
    assert response.status_code == 422


def test_export_honors_date_range(client, auth_headers):
    """The CSV must show exactly what the list shows — same window."""
    from datetime import timedelta

    from app.timezone import business_today

    create_order(client, auth_headers, customer_name="Export Today")
    today = business_today()
    past = today - timedelta(days=30)

    # Today's window exports the row; a past window exports nothing
    csv_today = client.get(
        f"/orders/export?start={today}&end={today}", headers=auth_headers
    ).text
    csv_past = client.get(
        f"/orders/export?start={past}&end={past}", headers=auth_headers
    ).text
    assert "Export Today" in csv_today
    assert "Export Today" not in csv_past


def test_get_order(client, auth_headers, order):
    response = client.get(f"/orders/{order['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["tracking_code"] == order["tracking_code"]


def test_update_order_fields(client, auth_headers, order):
    response = client.patch(
        f"/orders/{order['id']}",
        json={"customer_address": "New Address 42", "notes": "Updated note"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["customer_address"] == "New Address 42"
    assert response.json()["notes"] == "Updated note"


def test_update_order_phone(client, auth_headers, order):
    """The phone number is the most-mistyped field — it must be editable
    (P0 audit fix #4)."""
    response = client.patch(
        f"/orders/{order['id']}",
        json={"customer_phone": "01911112222"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["customer_phone"] == "01911112222"

    # And it's validated like on create — too-short is rejected
    response = client.patch(
        f"/orders/{order['id']}",
        json={"customer_phone": "123"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_update_order_recomputes_total(client, auth_headers, order):
    response = client.patch(
        f"/orders/{order['id']}",
        json={"items": [{"name": "Single", "quantity": 3, "price": 200}]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["total_price"] == 600


def test_status_happy_path(client, auth_headers, order):
    order_id = order["id"]
    for status in ("confirmed", "shipped", "delivered"):
        response = client.patch(
            f"/orders/{order_id}/status",
            json={"status": status},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status
    history = response.json()["status_history"]
    assert [event["status"] for event in history] == [
        "placed",
        "confirmed",
        "shipped",
        "delivered",
    ]


def test_status_cannot_skip_steps(client, auth_headers, order):
    response = client.patch(
        f"/orders/{order['id']}/status",
        json={"status": "delivered"},
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_status_cannot_repeat_current(client, auth_headers, order):
    response = client.patch(
        f"/orders/{order['id']}/status",
        json={"status": "placed"},
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_cancelled_order_is_terminal(client, auth_headers, order):
    order_id = order["id"]
    cancel = client.patch(
        f"/orders/{order_id}/status", json={"status": "cancelled"}, headers=auth_headers
    )
    assert cancel.status_code == 200
    # Cannot revive or edit a cancelled order
    revive = client.patch(
        f"/orders/{order_id}/status", json={"status": "confirmed"}, headers=auth_headers
    )
    assert revive.status_code == 409
    edit = client.patch(
        f"/orders/{order_id}", json={"notes": "too late"}, headers=auth_headers
    )
    assert edit.status_code == 409


def test_delivered_order_cannot_be_edited(client, auth_headers, order):
    order_id = order["id"]
    for status in ("confirmed", "shipped", "delivered"):
        client.patch(f"/orders/{order_id}/status", json={"status": status}, headers=auth_headers)
    response = client.patch(
        f"/orders/{order_id}", json={"notes": "late edit"}, headers=auth_headers
    )
    assert response.status_code == 409


def test_delete_order_only_while_placed(client, auth_headers, order):
    order_id = order["id"]
    deleted = client.delete(f"/orders/{order_id}", headers=auth_headers)
    assert deleted.status_code == 204
    gone = client.get(f"/orders/{order_id}", headers=auth_headers)
    assert gone.status_code == 404


def test_delete_rejected_after_progress(client, auth_headers, order):
    order_id = order["id"]
    client.patch(f"/orders/{order_id}/status", json={"status": "confirmed"}, headers=auth_headers)
    response = client.delete(f"/orders/{order_id}", headers=auth_headers)
    assert response.status_code == 409


def test_ownership_isolation(client, auth_headers, order):
    # A second seller must not see, edit, or advance the first seller's order
    client.post(
        "/auth/signup",
        json={
            "email": "intruder@example.com",
            "password": "intruderpass1",
            "store_name": "Intruder Store",
        },
    )
    login = client.post(
        "/auth/login", json={"email": "intruder@example.com", "password": "intruderpass1"}
    )
    intruder_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get(f"/orders/{order['id']}", headers=intruder_headers).status_code == 404
    assert (
        client.patch(
            f"/orders/{order['id']}/status", json={"status": "confirmed"}, headers=intruder_headers
        ).status_code
        == 404
    )
    # And their order list is empty — not the other seller's orders
    listing = client.get("/orders", headers=intruder_headers)
    assert listing.json()["total"] == 0


def test_orders_require_authentication(client):
    assert client.get("/orders").status_code == 401
    assert client.post("/orders", json={}).status_code == 401


def test_stats_route_not_swallowed_by_order_id(client, auth_headers):
    """Route ordering regression guard: /orders/stats/summary must not
    be matched by /orders/{order_id}."""
    response = client.get("/orders/stats/summary", headers=auth_headers)
    assert response.status_code == 200


# ---------- Order-number race condition (P0 audit fix) ----------

def test_duplicate_order_number_rejected_by_db(client, seller, auth_headers, order):
    """The database itself must refuse two orders with the same
    (seller_id, order_number) — the app-level retry depends on it."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.models import Order
    from conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        db.add(
            Order(
                seller_id=seller["id"],
                order_number=order["order_number"],  # deliberate duplicate
                tracking_code="DUP12345",
                customer_name="Dup",
                customer_phone="01800000000",
                items=[],
                total_price=0.0,
                status_history=[],
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_insert_retry_resolves_number_collision(client, seller, auth_headers):
    """When an insert loses the race, _insert_order_with_retry rebuilds
    the order with a fresh number instead of failing."""
    from app.models import Order
    from app.routes.orders import _insert_order_with_retry
    from conftest import TestingSessionLocal

    # The seller already has order #1 (the "other request" won the race)
    existing = create_order(client, auth_headers).json()
    assert existing["order_number"] == 1

    db = TestingSessionLocal()
    try:
        calls = []

        def build():
            calls.append(len(calls))
            # First attempt collides with the existing order #1,
            # second attempt takes the next free number
            number = 1 if len(calls) == 1 else 2
            return Order(
                seller_id=seller["id"],
                order_number=number,
                tracking_code=f"RT{len(calls)}00000"[:8],
                customer_name="Retry",
                customer_phone="01800000000",
                items=[],
                total_price=0.0,
                status_history=[],
            )

        order = _insert_order_with_retry(db, build)
        assert order.order_number == 2
        assert len(calls) == 2  # one collision, one success
    finally:
        db.close()


def test_sequential_orders_get_sequential_numbers(client, auth_headers):
    first = create_order(client, auth_headers).json()
    second = create_order(client, auth_headers).json()
    assert second["order_number"] == first["order_number"] + 1


# ---------- CSV export (audit fix #10) ----------

def _parse_csv(response):
    """Parse an export response body into (header, data_rows)."""
    import csv
    import io

    rows = list(csv.reader(io.StringIO(response.text.lstrip("\ufeff"))))
    return rows[0], rows[1:]


def test_export_requires_authentication(client):
    assert client.get("/orders/export").status_code == 401


def test_export_csv_roundtrip(client, auth_headers):
    """Addresses contain commas and quotes — the CSV must escape them
    so the file re-parses to the original values."""
    create_order(
        client,
        auth_headers,
        customer_address='Flat 4B, "Green" House, Road 12',
        notes="Ring the bell, 2nd floor",
    )
    response = client.get("/orders/export", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    header, data = _parse_csv(response)
    assert header[0] == "Order #"
    assert len(data) == 1
    row = dict(zip(header, data[0]))
    assert row["Address"] == 'Flat 4B, "Green" House, Road 12'
    assert row["Customer name"] == "Test Customer"
    assert row["Items"] == "Item x1"


def test_export_respects_status_filter(client, auth_headers):
    kept = create_order(client, auth_headers).json()
    create_order(client, auth_headers)
    cancelled = client.patch(
        f"/orders/{kept['id']}/status", json={"status": "cancelled"}, headers=auth_headers
    )
    assert cancelled.status_code == 200

    response = client.get("/orders/export?status=placed", headers=auth_headers)
    _header, data = _parse_csv(response)
    assert len(data) == 1  # only the still-placed order


def test_export_is_seller_isolated(client, auth_headers, order):
    """A second seller's export must not contain the first seller's orders."""
    client.post(
        "/auth/signup",
        json={
            "email": "exportintruder@example.com",
            "password": "intruderpass1",
            "store_name": "Export Intruder",
        },
    )
    login = client.post(
        "/auth/login", json={"email": "exportintruder@example.com", "password": "intruderpass1"}
    )
    intruder_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/orders/export", headers=intruder_headers)
    assert response.status_code == 200
    _header, data = _parse_csv(response)
    assert data == []  # header only — none of the other seller's orders


# ---------- Timezone consistency (audit fix #7) ----------

def test_business_timezone_day_boundary(client, auth_headers, order):
    """An order placed at 00:30 Dhaka time is 18:30 UTC the *previous*
    day. It must still count as "today" for the seller and appear on
    today's chart bar — not on yesterday's."""
    from datetime import datetime, timedelta, timezone as dt_timezone
    from zoneinfo import ZoneInfo

    from app.models import Order
    from app.timezone import business_today
    from conftest import TestingSessionLocal

    dhaka = ZoneInfo("Asia/Dhaka")
    today = business_today()
    yesterday_date = today - timedelta(days=1)
    local_morning = datetime(
        today.year, today.month, today.day, 0, 30, tzinfo=dhaka
    )
    stored_utc = (
        local_morning.astimezone(dt_timezone.utc).replace(tzinfo=None)
    )
    # Sanity: 00:30 Dhaka is 18:30 UTC of the previous day
    assert stored_utc.date() == yesterday_date

    db = TestingSessionLocal()
    try:
        row = db.get(Order, order["id"])
        row.created_at = stored_utc
        db.commit()
    finally:
        db.close()

    body = client.get("/orders/stats/summary?range=today", headers=auth_headers).json()
    assert body["total_orders"] == 1
    assert body["today_orders"] == 1
    assert body["daily"][0]["date"] == today.isoformat()
    assert body["daily"][0]["count"] == 1

    # And yesterday's window must NOT claim it
    yesterday = client.get(
        f"/orders/stats/summary?range=custom&start={yesterday_date.isoformat()}"
        f"&end={yesterday_date.isoformat()}",
        headers=auth_headers,
    ).json()
    assert yesterday["total_orders"] == 0
