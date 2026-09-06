"""Password reset flow tests."""

import re

import pytest


@pytest.fixture
def captured_email(monkeypatch):
    """Capture emails instead of sending them; expose (to, subject, body)."""
    sent = []

    def fake_send(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr("app.routes.auth.send_email", fake_send)
    return sent


def extract_token(body: str) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", body)
    assert match, f"reset link missing from email body:\n{body}"
    return match.group(1)


def test_forgot_password_unknown_email_same_response(client, captured_email):
    """Anti-enumeration: unknown and known emails give identical responses."""
    known = client.post("/auth/forgot-password", json={"email": "seller@example.com"})
    unknown = client.post("/auth/forgot-password", json={"email": "ghost@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    # And nothing was "sent" for the unknown address
    assert len(captured_email) == 0


def test_forgot_password_sends_reset_link(client, seller, seller_payload, captured_email):
    response = client.post(
        "/auth/forgot-password", json={"email": seller_payload["email"]}
    )
    assert response.status_code == 200

    assert len(captured_email) == 1
    email = captured_email[0]
    assert email["to"] == seller_payload["email"]
    assert "reset" in email["subject"].lower()
    assert extract_token(email["body"])


def test_reset_password_full_flow(client, seller, seller_payload, captured_email):
    client.post("/auth/forgot-password", json={"email": seller_payload["email"]})
    token = extract_token(captured_email[0]["body"])

    reset = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "brandnewpass99"},
    )
    assert reset.status_code == 200

    # Old password no longer works, the new one does
    old = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert old.status_code == 401
    new = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": "brandnewpass99"},
    )
    assert new.status_code == 200


def test_reset_invalidates_preexisting_tokens(client, seller, seller_payload, captured_email):
    """A session token minted BEFORE the reset must stop working —
    a stolen token can't outlive the owner resetting the password."""
    # Log in and grab a token. The 1.1s nap guarantees the token's
    # whole-second `iat` is strictly before the reset's cutoff second —
    # without it the test would flake when both land in one second.
    login = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": seller_payload["password"]},
    )
    assert login.status_code == 200
    old_token = login.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {old_token}"}
    assert client.get("/auth/me", headers=auth_headers).status_code == 200
    import time

    time.sleep(1.1)

    # Reset the password
    client.post("/auth/forgot-password", json={"email": seller_payload["email"]})
    token = extract_token(captured_email[0]["body"])
    reset = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "brandnewpass99"}
    )
    assert reset.status_code == 200

    # The pre-reset token is now rejected…
    assert client.get("/auth/me", headers=auth_headers).status_code == 401

    # …and a fresh login works again
    fresh = client.post(
        "/auth/login",
        json={"email": seller_payload["email"], "password": "brandnewpass99"},
    )
    assert fresh.status_code == 200
    fresh_headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    assert client.get("/auth/me", headers=fresh_headers).status_code == 200


def test_reset_token_is_single_use(client, seller, seller_payload, captured_email):
    client.post("/auth/forgot-password", json={"email": seller_payload["email"]})
    token = extract_token(captured_email[0]["body"])

    first = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "firstpass123"}
    )
    assert first.status_code == 200

    second = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "secondpass456"}
    )
    assert second.status_code == 400


def test_reset_with_garbage_token_rejected(client):
    response = client.post(
        "/auth/reset-password",
        json={"token": "not-a-real-token-at-all-123", "new_password": "somepass123"},
    )
    assert response.status_code == 400


def test_reset_with_expired_token_rejected(client, seller, seller_payload, captured_email):
    from datetime import timedelta

    from app.models import PasswordResetToken, utcnow
    from conftest import TestingSessionLocal

    client.post("/auth/forgot-password", json={"email": seller_payload["email"]})
    token = extract_token(captured_email[0]["body"])

    # Force the stored record into the past
    import hashlib

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = TestingSessionLocal()
    try:
        record = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.token_hash == token_hash)
            .one()
        )
        record.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "toolatepass1"}
    )
    assert response.status_code == 400


def test_reset_rejects_weak_password(client, seller, seller_payload, captured_email):
    client.post("/auth/forgot-password", json={"email": seller_payload["email"]})
    token = extract_token(captured_email[0]["body"])

    response = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "123"}
    )
    assert response.status_code == 422


def test_forgot_password_has_rate_limit_rule():
    """Email-bombing protection: the endpoint must be rate limited
    (the HTTP-level middleware is disabled in tests, so we verify the
    rule itself and exercise its limiter directly)."""
    from app.rate_limit import RULES, _limiters

    rule = next((r for r in RULES if r[0] == "/auth/forgot-password"), None)
    assert rule is not None, "/auth/forgot-password missing from rate limit rules"
    _prefix, _method, limit, _window = rule
    assert limit <= 5

    limiter = _limiters["/auth/forgot-password"]
    for _ in range(limit):
        assert limiter.allow("test-ip") is True
    assert limiter.allow("test-ip") is False
