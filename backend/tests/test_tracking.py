"""Public tracking endpoint tests — including privacy guarantees."""


def test_track_valid_code(client, order):
    response = client.get(f"/track/{order['tracking_code']}")
    assert response.status_code == 200
    body = response.json()
    assert body["store_name"] == "Test Store"
    assert body["order_number"] == order["order_number"]
    assert body["customer_name"] == order["customer_name"]
    assert body["status"] == "placed"


def test_tracking_never_leaks_sensitive_fields(client, order):
    """The public contract must not expose address, phone, or seller id."""
    response = client.get(f"/track/{order['tracking_code']}")
    body = response.json()
    for forbidden in ("customer_address", "customer_phone", "seller_id", "notes", "items"):
        assert forbidden not in body, f"{forbidden} leaked on public tracking!"


def test_track_invalid_code_404(client, order):
    response = client.get("/track/ZZZZ9999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_track_lowercase_code_still_works(client, order):
    response = client.get(f"/track/{order['tracking_code'].lower()}")
    assert response.status_code == 200


def test_track_code_with_surrounding_spaces(client, order):
    response = client.get(f"/track/ {order['tracking_code']} ")
    assert response.status_code == 200


def test_track_requires_no_authentication(client, order):
    """No Authorization header at all — customers never log in."""
    response = client.get(f"/track/{order['tracking_code']}")
    assert response.status_code == 200


def test_tracking_reflects_status_changes(client, auth_headers, order):
    client.patch(
        f"/orders/{order['id']}/status", json={"status": "confirmed"}, headers=auth_headers
    )
    response = client.get(f"/track/{order['tracking_code']}")
    assert response.json()["status"] == "confirmed"
    history_statuses = [event["status"] for event in response.json()["status_history"]]
    assert history_statuses == ["placed", "confirmed"]


def test_tracking_reflects_store_rename(client, auth_headers, order):
    client.patch(
        "/auth/me", json={"store_name": "Fresh New Name", "phone": None}, headers=auth_headers
    )
    response = client.get(f"/track/{order['tracking_code']}")
    assert response.json()["store_name"] == "Fresh New Name"
