"""Dashboard statistics tests."""


def test_stats_summary_counts(client, auth_headers):
    # Order 1: will be delivered
    first = client.post(
        "/orders",
        json={
            "customer_name": "A",
            "customer_phone": "01811111111",
            "items": [{"name": "X", "quantity": 1, "price": 500}],
        },
        headers=auth_headers,
    ).json()
    # Order 2: stays placed
    client.post(
        "/orders",
        json={
            "customer_name": "B",
            "customer_phone": "01822222222",
            "items": [{"name": "Y", "quantity": 2, "price": 250}],
        },
        headers=auth_headers,
    )
    # Order 3: will be cancelled
    third = client.post(
        "/orders",
        json={
            "customer_name": "C",
            "customer_phone": "01833333333",
            "items": [{"name": "Z", "quantity": 1, "price": 1000}],
        },
        headers=auth_headers,
    ).json()

    for status in ("confirmed", "shipped", "delivered"):
        client.patch(
            f"/orders/{first['id']}/status", json={"status": status}, headers=auth_headers
        )
    client.patch(f"/orders/{third['id']}/status", json={"status": "cancelled"}, headers=auth_headers)

    stats = client.get("/orders/stats/summary", headers=auth_headers).json()

    assert stats["total_orders"] == 3
    assert stats["today_orders"] == 3  # all created moments ago
    assert stats["pending_orders"] == 1  # order B (placed)
    assert stats["delivered_orders"] == 1
    assert stats["cancelled_orders"] == 1
    # Revenue excludes cancelled: 500 + 500 = 1000
    assert stats["revenue"] == 1000
    assert stats["status_counts"]["placed"] == 1

    # 30-day series (default "all" range caps the chart at 30 days),
    # today's bucket holds all three
    assert len(stats["daily"]) == 30
    assert stats["daily"][-1]["count"] == 3


def test_stats_are_seller_scoped(client, auth_headers):
    client.post(
        "/orders",
        json={
            "customer_name": "Mine",
            "customer_phone": "01811111111",
            "items": [{"name": "X", "quantity": 1, "price": 100}],
        },
        headers=auth_headers,
    )

    # A second seller sees only their own (empty) stats
    client.post(
        "/auth/signup",
        json={
            "email": "other-stats@example.com",
            "password": "otherstats123",
            "store_name": "Other Store",
        },
    )
    login = client.post(
        "/auth/login", json={"email": "other-stats@example.com", "password": "otherstats123"}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    stats = client.get("/orders/stats/summary", headers=other_headers).json()
    assert stats["total_orders"] == 0
    assert stats["revenue"] == 0


def test_stats_require_authentication(client):
    assert client.get("/orders/stats/summary").status_code == 401
