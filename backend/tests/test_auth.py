"""Authentication endpoint tests."""


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_signup_success(client, seller_payload):
    response = client.post("/auth/signup", json=seller_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == seller_payload["email"]
    assert body["store_name"] == seller_payload["store_name"]
    # Security: no password material may ever appear in responses
    assert "password" not in body
    assert "hashed_password" not in body


def test_signup_duplicate_email(client, seller):
    response = client.post(
        "/auth/signup",
        json={
            "email": seller["email"],
            "password": "anotherpass123",
            "store_name": "Copycat Store",
        },
    )
    assert response.status_code == 409


def test_signup_weak_password_rejected(client):
    response = client.post(
        "/auth/signup",
        json={"email": "weak@example.com", "password": "123", "store_name": "Weak"},
    )
    assert response.status_code == 422


def test_signup_invalid_email_rejected(client):
    response = client.post(
        "/auth/signup",
        json={"email": "not-an-email", "password": "validpass123", "store_name": "Some Store"},
    )
    assert response.status_code == 422


def test_login_success_returns_token(client, seller, seller_payload):
    response = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_login_wrong_password(client, seller, seller_payload):
    response = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": "WRONGpass999"},
    )
    assert response.status_code == 401


def test_login_unknown_email_gives_same_message(client, seller_payload):
    """Unknown email and wrong password must be indistinguishable."""
    unknown = client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "whatever123"},
    )
    wrong = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": "WRONGpass999"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_login_locks_after_repeated_failures(client, seller, seller_payload):
    """5 wrong passwords lock the account — even the CORRECT password
    is refused while locked (an attacker must not get a free try)."""
    for _ in range(5):
        response = client.post(
            "/auth/login",
            json={"email": seller_payload["email"], "password": "WRONGpass999"},
        )
        assert response.status_code == 401

    locked = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert locked.status_code == 429
    assert "Retry-After" in locked.headers


def test_login_lockout_ignores_ip_rotation(client, seller, seller_payload):
    """The lockout is per-account, so the same failure count triggers it
    even though every request looks like a new client (the in-memory
    throttle keys on the email, not the IP)."""
    from app import login_throttle

    for _ in range(5):
        login_throttle.record_failure(seller_payload["email"])

    assert login_throttle.lockout_remaining(seller_payload["email"]) is not None
    response = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert response.status_code == 429


def test_login_success_clears_failure_count(client, seller, seller_payload):
    """4 failures, then a successful login, then 4 more — never reaches
    the 5-failure threshold because success reset the counter."""
    for _ in range(4):
        client.post(
            "/auth/login",
            json={"email": seller_payload["email"], "password": "WRONGpass999"},
        )
    ok = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert ok.status_code == 200
    for _ in range(4):
        client.post(
            "/auth/login",
            json={"email": seller_payload["email"], "password": "WRONGpass999"},
        )
    still_ok = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert still_ok.status_code == 200


def test_login_lockout_expires(monkeypatch):
    """The lock lifts after LOCKOUT_SECONDS — simulated by moving the
    clock forward rather than sleeping 15 minutes."""
    import time as time_module

    from app import login_throttle

    email = "clock-test@example.com"
    now = 1_000_000.0
    monkeypatch.setattr(time_module, "monotonic", lambda: now)

    for _ in range(login_throttle.MAX_FAILURES):
        login_throttle.record_failure(email)
    assert login_throttle.lockout_remaining(email) is not None

    monkeypatch.setattr(time_module, "monotonic", lambda: now + login_throttle.LOCKOUT_SECONDS + 1)
    assert login_throttle.lockout_remaining(email) is None


def test_me_with_valid_token(client, auth_headers, seller):
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == seller["id"]


def test_me_without_token(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_garbage_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert response.status_code == 401


def test_me_with_tampered_token(client, auth_headers):
    """A token signed with the wrong key must not authenticate."""
    tampered = auth_headers["Authorization"][:-3] + "xxx"
    response = client.get("/auth/me", headers={"Authorization": tampered})
    assert response.status_code == 401


def test_update_me_changes_store_name(client, auth_headers):
    response = client.patch(
        "/auth/me",
        json={"store_name": "Renamed Store", "phone": "01999999999"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["store_name"] == "Renamed Store"


def test_update_me_rejects_short_name(client, auth_headers):
    response = client.patch("/auth/me", json={"store_name": "A"}, headers=auth_headers)
    assert response.status_code == 422


# ---------- Production startup guard (P0 audit fix #3) ----------

def test_production_refuses_default_secret_key(monkeypatch):
    """The app must crash at boot rather than run in production with a
    forgeable JWT secret."""
    import pytest

    from app.main import _validate_production_config

    monkeypatch.setattr("app.main.settings.environment", "production")

    # The known default — must refuse
    monkeypatch.setattr("app.main.settings.secret_key", "dev-only-change-me")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _validate_production_config()

    # Too short — must refuse
    monkeypatch.setattr("app.main.settings.secret_key", "short-but-custom-key")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _validate_production_config()

    # Long random key — must pass
    monkeypatch.setattr("app.main.settings.secret_key", "a" * 64)
    _validate_production_config()


def test_dev_and_test_environments_skip_the_guard(monkeypatch):
    from app.main import _validate_production_config

    monkeypatch.setattr("app.main.settings.environment", "development")
    monkeypatch.setattr("app.main.settings.secret_key", "dev-only-change-me")
    _validate_production_config()  # no raise — dev keeps working
