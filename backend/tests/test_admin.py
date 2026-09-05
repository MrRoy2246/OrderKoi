"""Admin panel & subscription plan tests.

Real-world model: the admin is a *separate* platform account — not a
promoted shop owner. Admins manage the platform; sellers run shops.
(admin fixtures live in conftest.py — shared with other test modules.)
"""

import uuid
from datetime import timedelta

import pytest


# ---------- Access control ----------

def test_admin_endpoints_forbidden_for_normal_sellers(client, auth_headers):
    assert client.get("/admin/sellers", headers=auth_headers).status_code == 403
    assert client.get("/admin/stats", headers=auth_headers).status_code == 403


def test_admin_endpoints_require_authentication(client):
    assert client.get("/admin/sellers").status_code == 401


def test_signup_can_not_grant_admin_role(client, seller_payload):
    """Role is server-controlled — a crafted signup payload is ignored."""
    response = client.post(
        "/auth/signup", json={**seller_payload, "role": "admin", "plan": "pro"}
    )
    assert response.status_code == 201
    assert response.json()["role"] == "seller"
    assert response.json()["plan"] == "free"


def test_admin_cannot_create_orders(client, admin_headers):
    """Platform accounts don't run shops — order creation is blocked."""
    response = client.post(
        "/orders",
        json={
            "customer_name": "Should Fail",
            "customer_phone": "01800000000",
            "items": [{"name": "X", "quantity": 1, "price": 10}],
        },
        headers=admin_headers,
    )
    assert response.status_code == 403
    assert "platform accounts" in response.json()["detail"].lower()


# ---------- Admin endpoints ----------

def test_admin_sees_all_sellers(client, admin_headers, auth_headers, seller):
    response = client.get("/admin/sellers", headers=admin_headers)
    assert response.status_code == 200
    sellers = response.json()
    emails = {entry["email"] for entry in sellers}
    assert seller["email"] in emails
    admin_entry = next(entry for entry in sellers if entry["role"] == "admin")
    assert admin_entry["plan"] == "pro"


def test_admin_seller_entries_include_usage(client, admin_headers, auth_headers, order):
    response = client.get("/admin/sellers", headers=admin_headers)
    entry = next(s for s in response.json() if s["orders_count"] > 0)
    assert entry["orders_count"] == 1
    assert entry["revenue"] == 1400  # the conftest order total


def test_platform_stats(client, admin_headers, auth_headers, seller, order):
    stats = client.get("/admin/stats", headers=admin_headers).json()
    assert stats["total_sellers"] >= 1
    assert stats["total_orders"] >= 1
    assert stats["platform_revenue"] >= 1400
    assert stats["pro_sellers"] + stats["free_sellers"] == stats["total_sellers"]


def test_platform_stats_growth_pulse(client, admin_headers, auth_headers, seller, order):
    """The conftest order + seller are both fresh, so they land in the
    month window and the 30-day signup window."""
    stats = client.get("/admin/stats", headers=admin_headers).json()
    assert stats["orders_this_month"] >= 1
    assert stats["gmv_this_month"] >= 1400
    assert stats["new_sellers_30d"] >= 1


def test_platform_stats_recent_signups(client, admin_headers, auth_headers, seller):
    stats = client.get("/admin/stats", headers=admin_headers).json()
    signups = stats["recent_signups"]
    assert 1 <= len(signups) <= 5
    # The just-created seller is the newest shop on the platform
    assert signups[0]["store_name"] == seller["store_name"]
    assert signups[0]["plan"] == "free"
    assert signups[0]["created_at"]
    # Newest first — created_at is descending
    dates = [s["created_at"] for s in signups]
    assert dates == sorted(dates, reverse=True)


def test_platform_stats_old_month_activity_excluded(client, admin_headers, seller):
    """An order from a previous business month counts toward totals but
    not toward the "this month" strip."""
    from datetime import timedelta

    from app.models import Order, Seller
    from app.timezone import month_start_utc
    from conftest import TestingSessionLocal

    # The suite shares one DB, so other tests' fresh orders may already
    # be in this month's window — compare before/after instead of
    # asserting absolute zeros
    before = client.get("/admin/stats", headers=admin_headers).json()

    db = TestingSessionLocal()
    try:
        # A separate shop so the auth seller's own (fresh) orders — if
        # any — can't muddy the this-month assertions
        old_seller = Seller(
            email=f"old-shop-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="x",
            store_name="Last Month Shop",
            store_slug=f"old-shop-{uuid.uuid4().hex[:8]}",
            role="seller",
            plan="free",
        )
        db.add(old_seller)
        db.flush()
        db.add(
            Order(
                seller_id=old_seller.id,
                order_number=1,
                tracking_code=f"OLD{uuid.uuid4().hex[:8].upper()}",
                customer_name="Last Month",
                customer_phone="01800000000",
                items=[{"name": "Old thing", "quantity": 1, "price": 500}],
                total_price=500,
                created_at=month_start_utc() - timedelta(days=1),
            )
        )
        db.commit()
    finally:
        db.close()

    stats = client.get("/admin/stats", headers=admin_headers).json()
    # The backdated order appears in all-time numbers…
    assert stats["total_orders"] == before["total_orders"] + 1
    assert stats["platform_revenue"] >= before["platform_revenue"] + 500
    # …but not in this month's strip
    assert stats["orders_this_month"] == before["orders_this_month"]
    assert stats["gmv_this_month"] == before["gmv_this_month"]
    # The shops themselves were created just now — recent signups
    assert stats["new_sellers_30d"] == before["new_sellers_30d"] + 1


def test_admin_changes_seller_plan(client, admin_headers, auth_headers, seller):
    response = client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["plan"] == "pro"

    # The seller sees their new plan immediately
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["plan"] == "pro"


def test_admin_cannot_downgrade_themselves(client, admin_headers):
    me = client.get("/auth/me", headers=admin_headers).json()
    response = client.patch(
        f"/admin/sellers/{me['id']}/plan", json={"plan": "free"}, headers=admin_headers
    )
    assert response.status_code == 409


# ---------- Manual Pro activation with duration ----------

def test_admin_upgrade_with_months_sets_expiry(client, admin_headers, auth_headers, seller):
    from datetime import datetime, timedelta

    response = client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 1},
        headers=admin_headers,
    )
    assert response.status_code == 200
    expiry = datetime.fromisoformat(response.json()["plan_expires_at"])
    # ~1 month from now (same time-of-day, calendar month later)
    now = datetime.now(expiry.tzinfo) if expiry.tzinfo else datetime.utcnow()
    assert timedelta(days=27) < expiry - now < timedelta(days=32)

    # The seller sees the new plan and expiry immediately
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["plan"] == "pro"
    assert me["plan_expires_at"] == response.json()["plan_expires_at"]


def test_admin_extend_active_pro_stacks_from_current_expiry(client, admin_headers, seller):
    """Extending an active Pro must add months to the current expiry —
    never reset it to today + months (paid time is never lost)."""
    from datetime import datetime

    first = client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 1},
        headers=admin_headers,
    ).json()
    second = client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 6},
        headers=admin_headers,
    ).json()

    e1 = datetime.fromisoformat(first["plan_expires_at"])
    e2 = datetime.fromisoformat(second["plan_expires_at"])
    # 6 months ≈ 181–184 days stacked on top of the first expiry
    assert e2 > e1
    assert 180 <= (e2 - e1).days <= 185


def test_admin_upgrade_records_ledger_event(client, admin_headers, seller):
    client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 6},
        headers=admin_headers,
    )
    events = client.get("/admin/subscription-events", headers=admin_headers).json()
    mine = [e for e in events if e["seller_id"] == seller["id"]]
    assert mine, "expected a ledger entry for the manual activation"
    assert mine[0]["event"] == "subscribed"
    assert mine[0]["months"] == 6
    assert "manually" in mine[0]["note"]


def test_admin_upgrade_invalid_months_rejected(client, admin_headers, seller):
    response = client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 3},  # only 1 / 6 / 12 are valid
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_plan_change_unknown_seller_404(client, admin_headers):
    response = client.patch(
        "/admin/sellers/999999/plan", json={"plan": "pro"}, headers=admin_headers
    )
    assert response.status_code == 404


# ---------- Comp (free Pro) grants ----------

def test_admin_comp_grant_marks_ledger_and_excludes_revenue(client, admin_headers, auth_headers, seller):
    """A comp grant gives Pro like a normal one — but the ledger row is
    flagged comp and subscription revenue ignores it entirely.
    (The suite DB is shared, so revenue is compared before/after.)"""
    before = client.get("/admin/stats", headers=admin_headers).json()

    response = client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 1, "comp": True},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["plan"] == "pro"

    # Ledger: flagged comp
    events = client.get("/admin/subscription-events", headers=admin_headers).json()
    mine = [e for e in events if e["seller_id"] == seller["id"]]
    assert mine and mine[0]["comp"] is True
    assert "free" in mine[0]["note"]

    # Revenue: nothing counted from the comp grant
    stats = client.get("/admin/stats", headers=admin_headers).json()
    assert stats["subscription_revenue_total"] == before["subscription_revenue_total"]
    assert stats["subscription_revenue_30d"] == before["subscription_revenue_30d"]


def test_paid_activation_counts_in_subscription_revenue(client, admin_headers, seller):
    """Paid manual activations DO count toward subscription revenue."""
    before = client.get("/admin/stats", headers=admin_headers).json()
    client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 1},
        headers=admin_headers,
    )
    stats = client.get("/admin/stats", headers=admin_headers).json()
    assert stats["subscription_revenue_total"] == before["subscription_revenue_total"] + 399
    assert stats["subscription_revenue_30d"] == before["subscription_revenue_30d"] + 399


def test_comp_default_false_and_cumulative_revenue(client, admin_headers, seller):
    """Normal grants don't set comp, and revenue sums across entries."""
    before = client.get("/admin/stats", headers=admin_headers).json()
    client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 12},
        headers=admin_headers,
    )
    events = client.get("/admin/subscription-events", headers=admin_headers).json()
    mine = [e for e in events if e["seller_id"] == seller["id"]]
    assert mine and mine[0]["comp"] is False

    stats = client.get("/admin/stats", headers=admin_headers).json()
    assert stats["subscription_revenue_total"] == before["subscription_revenue_total"] + 3299


# ---------- Stats: chart series ----------

def test_platform_stats_chart_series_shapes(client, admin_headers, auth_headers, seller, order):
    stats = client.get("/admin/stats", headers=admin_headers).json()

    # 30 daily buckets ending today by default
    assert len(stats["orders_daily"]) == 30
    assert stats["orders_daily"][-1]["count"] >= 1  # the conftest order

    # The days filter scopes the daily series (7 / 90, clamped)
    assert len(client.get("/admin/stats?days=7", headers=admin_headers).json()["orders_daily"]) == 7
    assert len(client.get("/admin/stats?days=90", headers=admin_headers).json()["orders_daily"]) == 90
    assert len(client.get("/admin/stats?days=9999", headers=admin_headers).json()["orders_daily"]) == 90

    # The money/growth series follow the SAME filter with daily
    # granularity for the default (<= 90 day) window — one bucket per
    # day, matching the orders chart exactly
    assert len(stats["revenue_monthly"]) == 30
    assert len(stats["sellers_monthly"]) == 30
    assert len(stats["subscription_monthly"]) == 30
    keys = [b["date"] for b in stats["revenue_monthly"]]
    assert keys == sorted(keys)
    assert [b["date"] for b in stats["subscription_monthly"]] == keys
    assert keys[-1] == stats["orders_daily"][-1]["date"]
    # Today's bucket (Asia/Dhaka) holds the fresh order's GMV
    assert stats["revenue_monthly"][-1]["value"] >= 1400
    # And the fresh signup
    assert stats["sellers_monthly"][-1]["count"] >= 1


def test_platform_stats_wide_window_monthly_series(client, admin_headers, auth_headers, seller, order):
    """A window wider than 90 days (the year presets) switches the
    money/growth series to monthly buckets, scoped to the window."""
    from datetime import date as date_cls

    from app.timezone import business_today

    end = business_today()
    start = date_cls(end.year, 1, 1)
    stats = client.get(
        f"/admin/stats?start={start.isoformat()}&end={end.isoformat()}",
        headers=admin_headers,
    ).json()
    # Monthly keys, oldest first, all inside the window's months
    buckets = stats["revenue_monthly"]
    assert len(buckets) >= 2
    keys = [b["month"] for b in buckets]
    assert keys == sorted(keys)
    assert keys[-1] == f"{end.year:04d}-{end.month:02d}"
    assert keys[0] == f"{start.year:04d}-{start.month:02d}"
    assert all(b["date"] is None for b in buckets)
    # The fresh order lands in the window's last month
    assert buckets[-1]["value"] >= 1400
    assert stats["sellers_monthly"][-1]["count"] >= 1  # the fresh signup


# ---------- Stats: custom date range ----------

def test_platform_stats_custom_range_shape(client, admin_headers, seller, order):
    """A custom range returns exactly one bucket per day, in order,
    with the fresh order landing on today's (the end date's) bucket."""
    from datetime import date as date_cls

    from app.timezone import business_today

    end = business_today()
    start = date_cls.fromordinal(end.toordinal() - 6)
    stats = client.get(
        f"/admin/stats?start={start.isoformat()}&end={end.isoformat()}",
        headers=admin_headers,
    ).json()
    daily = stats["orders_daily"]
    assert len(daily) == 7
    assert [d["date"] for d in daily] == [
        date_cls.fromordinal(start.toordinal() + i).isoformat() for i in range(7)
    ]
    assert daily[-1]["count"] >= 1  # the conftest order is on today's bucket


def test_platform_stats_custom_range_validations(client, admin_headers):
    """Missing half, reversed order, and >1 year are all 422s."""
    base = "/admin/stats"
    # Missing end
    assert client.get(f"{base}?start=2026-01-01", headers=admin_headers).status_code == 422
    # Reversed
    assert (
        client.get(f"{base}?start=2026-02-01&end=2026-01-01", headers=admin_headers).status_code
        == 422
    )
    # More than a year
    assert (
        client.get(
            f"{base}?start=2024-01-01&end=2026-01-01", headers=admin_headers
        ).status_code
        == 422
    )


def test_platform_stats_custom_range_excludes_today(client, admin_headers, auth_headers, seller):
    """A custom range ending yesterday doesn't see an order placed today —
    inclusive bounds in the business timezone, no off-by-one. (Shared DB:
    other tests may have backdated orders inside the window, so the
    assertion is a before/after delta, not absolute zeros.)"""
    from datetime import timedelta

    from app.timezone import business_today

    end = business_today() - timedelta(days=1)
    start = end - timedelta(days=6)
    query = f"?start={start.isoformat()}&end={end.isoformat()}"

    before = client.get(f"/admin/stats{query}", headers=admin_headers).json()
    in_window_before = sum(d["count"] for d in before["orders_daily"])

    response = client.post(
        "/orders",
        json={
            "customer_name": "Window Test",
            "customer_phone": "01800000000",
            "items": [{"name": "X", "quantity": 1, "price": 10}],
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    after = client.get(f"/admin/stats{query}", headers=admin_headers).json()
    assert sum(d["count"] for d in after["orders_daily"]) == in_window_before


def test_subscription_monthly_tracks_paid_grants(client, admin_headers, seller):
    """A paid activation lands in today's bucket (daily granularity on
    the default window); comp grants never do."""
    before = client.get("/admin/stats", headers=admin_headers).json()
    client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 6},
        headers=admin_headers,
    )
    client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 1, "comp": True},
        headers=admin_headers,
    )
    stats = client.get("/admin/stats", headers=admin_headers).json()
    # Today's bucket gained only the paid 6-month price
    assert (
        stats["subscription_monthly"][-1]["value"]
        == before["subscription_monthly"][-1]["value"] + 1999
    )
    # And the total agrees with the month series sum
    assert stats["subscription_revenue_total"] >= sum(
        m["value"] for m in stats["subscription_monthly"]
    )


def test_platform_stats_comp_revenue_mixed(client, admin_headers, seller):
    """Paid + comp grants: only the paid money shows up."""
    before = client.get("/admin/stats", headers=admin_headers).json()
    client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 1},
        headers=admin_headers,
    )
    client.patch(
        f"/admin/sellers/{seller['id']}/plan",
        json={"plan": "pro", "months": 6, "comp": True},
        headers=admin_headers,
    )
    stats = client.get("/admin/stats", headers=admin_headers).json()
    # only the paid month, not the comped 6 months
    assert stats["subscription_revenue_total"] == before["subscription_revenue_total"] + 399


# ---------- Seller stats: daily revenue series ----------

def test_stats_daily_series_includes_revenue(client, auth_headers, order):
    """Each daily bucket now carries the day's non-cancelled revenue."""
    summary = client.get("/orders/stats/summary?range=7d", headers=auth_headers).json()
    today = summary["daily"][-1]
    assert today["count"] >= 1
    assert today["value"] >= 1400  # the conftest order total
    # Every bucket has both fields
    assert all("value" in day and "count" in day for day in summary["daily"])


def test_stats_daily_revenue_excludes_cancelled(client, auth_headers, order):
    """Cancelling an order removes it from the day's revenue bucket."""
    client.patch(
        f"/orders/{order['id']}/status", json={"status": "cancelled"}, headers=auth_headers
    )
    summary = client.get("/orders/stats/summary?range=7d", headers=auth_headers).json()
    today = summary["daily"][-1]
    assert today["value"] == 0
    assert summary["revenue"] == 0


def test_free_plan_monthly_limit_enforced(client, auth_headers, monkeypatch):
    from app.routes import orders as orders_module

    # Shrink the limit so the test stays fast
    monkeypatch.setattr(orders_module.settings, "free_plan_monthly_orders", 2)

    for _ in range(2):
        response = client.post(
            "/orders",
            json={
                "customer_name": "Limit Test",
                "customer_phone": "01800000000",
                "items": [{"name": "X", "quantity": 1, "price": 10}],
            },
            headers=auth_headers,
        )
        assert response.status_code == 201

    blocked = client.post(
        "/orders",
        json={
            "customer_name": "Limit Test",
            "customer_phone": "01800000000",
            "items": [{"name": "X", "quantity": 1, "price": 10}],
        },
        headers=auth_headers,
    )
    assert blocked.status_code == 403
    assert "Free plan limit reached" in blocked.json()["detail"]


def test_cancelled_orders_dont_burn_quota(client, auth_headers, monkeypatch):
    """Cancelling an order refunds its quota unit (audit fix #8) — a
    seller who cancels mistakes or form spam isn't punished for it."""
    from app.routes import orders as orders_module

    monkeypatch.setattr(orders_module.settings, "free_plan_monthly_orders", 1)

    payload = {
        "customer_name": "Quota Test",
        "customer_phone": "01800000000",
        "items": [{"name": "X", "quantity": 1, "price": 10}],
    }

    first = client.post("/orders", json=payload, headers=auth_headers)
    assert first.status_code == 201
    order_id = first.json()["id"]

    # Quota of 1 is now spent
    blocked = client.post("/orders", json=payload, headers=auth_headers)
    assert blocked.status_code == 403

    # Cancelling the order frees the unit again
    cancel = client.patch(
        f"/orders/{order_id}/status", json={"status": "cancelled"}, headers=auth_headers
    )
    assert cancel.status_code == 200
    assert client.post("/orders", json=payload, headers=auth_headers).status_code == 201


def test_pro_plan_bypasses_limit(client, auth_headers, monkeypatch):
    from app.models import Seller
    from conftest import TestingSessionLocal

    from app.routes import orders as orders_module

    monkeypatch.setattr(orders_module.settings, "free_plan_monthly_orders", 1)

    # Promote the seller to pro directly in the DB
    db = TestingSessionLocal()
    try:
        me = client.get("/auth/me", headers=auth_headers).json()
        db.query(Seller).filter(Seller.id == me["id"]).update({"plan": "pro"})
        db.commit()
    finally:
        db.close()

    for _ in range(3):  # over the free limit — pro allows it
        response = client.post(
            "/orders",
            json={
                "customer_name": "Pro Test",
                "customer_phone": "01800000001",
                "items": [{"name": "X", "quantity": 1, "price": 10}],
            },
            headers=auth_headers,
        )
        assert response.status_code == 201


# ---------- Per-shop stats (admin drill-down) ----------

def test_seller_shop_stats_default_window(client, admin_headers, seller, order):
    """The default window is the trailing 30 days: one bucket per day,
    the fresh order in today's bucket, and the shop's fields present."""
    stats = client.get(
        f"/admin/sellers/{seller['id']}/stats", headers=admin_headers
    ).json()
    assert stats["store_name"] == seller["store_name"]
    assert stats["email"] == seller["email"]
    assert len(stats["daily"]) == 30
    assert stats["daily"][-1]["count"] >= 1  # the conftest order, placed today
    assert stats["daily"][-1]["value"] >= 1400
    assert stats["total_orders"] >= 1
    assert stats["revenue"] >= 1400
    assert stats["aov"] == round(stats["revenue"] / stats["total_orders"], 2)
    assert stats["status_counts"]["placed"] >= 1


def test_seller_shop_stats_custom_range_excludes_other_seller(
    client, admin_headers, auth_headers, seller, order
):
    """The shop's stats only count its own orders; a second seller's
    order placed inside the window must not leak in. (Shared DB: other
    tests' orders may exist for OTHER sellers, but none for this one
    — it was created in this test.)"""
    import uuid as uuid_mod

    # A second shop with one order today
    other_payload = {
        "email": f"shopstats-{uuid_mod.uuid4().hex[:10]}@example.com",
        "password": "secretpass123",
        "store_name": "Other Shop",
        "phone": "01712345679",
    }
    signup = client.post("/auth/signup", json=other_payload)
    assert signup.status_code == 201
    other_login = client.post(
        "/auth/login",
        json={"email": other_payload["email"], "password": "password" if False else "secretpass123"},
    )
    assert other_login.status_code == 200
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    other_order = client.post(
        "/orders",
        json={
            "customer_name": "Other Buyer",
            "customer_phone": "01899999999",
            "items": [{"name": "Y", "quantity": 1, "price": 200}],
        },
        headers=other_headers,
    )
    assert other_order.status_code == 201

    # First seller's stats see only the conftest order (1,400 Tk), not
    # the other shop's 200 Tk one
    stats = client.get(
        f"/admin/sellers/{seller['id']}/stats", headers=admin_headers
    ).json()
    assert stats["total_orders"] == 1
    assert stats["revenue"] == 1400


def test_seller_shop_stats_validations(client, admin_headers, seller):
    """Missing half, reversed, over a year — same 422 rules as the
    platform stats."""
    base = f"/admin/sellers/{seller['id']}/stats"
    assert client.get(f"{base}?start=2026-01-01", headers=admin_headers).status_code == 422
    assert (
        client.get(f"{base}?start=2026-02-01&end=2026-01-01", headers=admin_headers).status_code
        == 422
    )
    assert (
        client.get(
            f"{base}?start=2024-01-01&end=2026-01-01", headers=admin_headers
        ).status_code
        == 422
    )


def test_seller_shop_stats_unknown_seller_404(client, admin_headers):
    assert (
        client.get("/admin/sellers/999999/stats", headers=admin_headers).status_code == 404
    )


def test_seller_shop_stats_forbidden_for_seller(client, auth_headers, seller):
    """A normal seller can't inspect another shop — admin only."""
    response = client.get(f"/admin/sellers/{seller['id']}/stats", headers=auth_headers)
    assert response.status_code == 403


def test_seller_orders_csv_export(client, admin_headers, seller, order):
    """The CSV export honors the shop scoping and the window, and the
    BOM header row is present for Excel."""
    from datetime import date as date_cls

    from app.timezone import business_today

    end = business_today()
    start = date_cls.fromordinal(end.toordinal() - 6)
    response = client.get(
        f"/admin/sellers/{seller['id']}/orders.csv"
        f"?start={start.isoformat()}&end={end.isoformat()}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert body.startswith("﻿")
    assert "Order #" in body
    assert "Rahim Uddin" in body  # the conftest order's customer
    assert seller["store_slug"] in response.headers["content-disposition"]


def test_seller_orders_csv_excludes_other_shops(client, admin_headers, seller, auth_headers, order):
    """A second shop's order must not appear in this shop's CSV."""
    import uuid as uuid_mod

    other_payload = {
        "email": f"shopcsv-{uuid_mod.uuid4().hex[:10]}@example.com",
        "password": "secretpass123",
        "store_name": "CSV Other Shop",
        "phone": "01712345676",
    }
    client.post("/auth/signup", json=other_payload)
    other_login = client.post(
        "/auth/login",
        json={"email": other_payload["email"], "password": other_payload["password"]},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    other = client.post(
        "/orders",
        json={
            "customer_name": "CSV Excluded Buyer",
            "customer_phone": "01888888888",
            "items": [{"name": "Z", "quantity": 1, "price": 100}],
        },
        headers=other_headers,
    )
    assert other.status_code == 201

    response = client.get(
        f"/admin/sellers/{seller['id']}/orders.csv", headers=admin_headers
    )
    assert response.status_code == 200
    assert "Rahim Uddin" in response.text
    assert "CSV Excluded Buyer" not in response.text
