"""Email verification flow tests.

The signup → welcome email → verify link → login gate flow, plus the
resend endpoint's anti-enumeration behaviour. Customer-facing order
emails (order received / status changed) live in test_public.py and
test_orders.py next to the flows that trigger them.
"""

import hashlib
import re
from datetime import timedelta

import pytest

from conftest import TestingSessionLocal


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
    assert match, f"verification link missing from email body:\n{body}"
    return match.group(1)


def signup_raw(client, payload):
    """Signup without the conftest fixture — the account starts
    unverified, which is exactly what these tests need."""
    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


# ---------- Signup sends the welcome + verification email ----------

def test_signup_sends_welcome_verification_email(client, seller_payload, captured_email):
    signup_raw(client, seller_payload)

    assert len(captured_email) == 1
    email = captured_email[0]
    assert email["to"] == seller_payload["email"]
    assert "verify" in email["subject"].lower()
    assert seller_payload["store_name"] in email["body"]
    assert extract_token(email["body"])


def test_signup_response_reports_unverified(client, seller_payload):
    body = signup_raw(client, seller_payload)
    assert body["email_verified"] is False


# ---------- Login gate ----------

def test_login_blocked_before_verification(client, seller_payload, captured_email):
    signup_raw(client, seller_payload)
    response = login(client, seller_payload["email"], seller_payload["password"])
    assert response.status_code == 403
    assert "verify" in response.json()["detail"].lower()


def test_login_allowed_after_verification(client, seller_payload, captured_email):
    signup_raw(client, seller_payload)
    token = extract_token(captured_email[0]["body"])

    verified = client.get(f"/auth/verify-email?token={token}")
    assert verified.status_code == 200

    response = login(client, seller_payload["email"], seller_payload["password"])
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_fixture_accounts_are_verified(client, seller, seller_payload, auth_headers):
    """The conftest seller fixture pre-verifies — guard that contract so
    the rest of the suite can keep logging in."""
    assert login(client, seller_payload["email"], seller_payload["password"]).status_code == 200
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["email_verified"] is True


# ---------- Token validity ----------

def test_verify_email_full_flow_marks_account(client, seller_payload, captured_email):
    from app.models import Seller

    signup_raw(client, seller_payload)
    token = extract_token(captured_email[0]["body"])

    assert client.get(f"/auth/verify-email?token={token}").status_code == 200

    db = TestingSessionLocal()
    try:
        seller = db.query(Seller).filter(Seller.email == seller_payload["email"]).first()
        assert seller.email_verified is True
    finally:
        db.close()


def test_verification_token_is_single_use(client, seller_payload, captured_email):
    """A consumed token can't verify anything new — but replaying it
    (double-click, page refresh) still reports success, since the
    account it verified is already verified."""
    signup_raw(client, seller_payload)
    token = extract_token(captured_email[0]["body"])

    assert client.get(f"/auth/verify-email?token={token}").status_code == 200
    replay = client.get(f"/auth/verify-email?token={token}")
    assert replay.status_code == 200
    assert "already verified" in replay.json()["detail"]

    from app.models import Seller

    db = TestingSessionLocal()
    try:
        seller = db.query(Seller).filter(Seller.email == seller_payload["email"]).first()
        assert seller.email_verified is True  # replay didn't flip it back
    finally:
        db.close()


def test_used_token_with_unverified_account_rejected(client, seller_payload, captured_email):
    """A consumed token whose account somehow never got verified must
    not silently pass — request a fresh link instead."""
    signup_raw(client, seller_payload)
    token = extract_token(captured_email[0]["body"])

    assert client.get(f"/auth/verify-email?token={token}").status_code == 200

    from app.models import Seller

    db = TestingSessionLocal()
    try:
        seller = db.query(Seller).filter(Seller.email == seller_payload["email"]).first()
        seller.email_verified = False  # simulate the odd state
        db.commit()
    finally:
        db.close()

    replay = client.get(f"/auth/verify-email?token={token}")
    assert replay.status_code == 400


def test_expired_verification_token_rejected(client, seller_payload, captured_email):
    from app.models import EmailVerificationToken, utcnow

    signup_raw(client, seller_payload)
    token = extract_token(captured_email[0]["body"])

    # Age the token past its window directly in the DB
    db = TestingSessionLocal()
    try:
        record = (
            db.query(EmailVerificationToken)
            .filter(EmailVerificationToken.token_hash == hashlib.sha256(token.encode()).hexdigest())
            .first()
        )
        assert record is not None
        record.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/auth/verify-email?token={token}")
    assert response.status_code == 400
    # And the account is still locked out
    assert login(client, seller_payload["email"], seller_payload["password"]).status_code == 403


def test_garbage_verification_token_rejected(client):
    response = client.get("/auth/verify-email?token=" + "x" * 43)
    assert response.status_code == 400


def test_missing_verification_token_rejected(client):
    response = client.get("/auth/verify-email")
    assert response.status_code == 422  # FastAPI: required query param absent


# ---------- Resend ----------

def test_resend_unknown_email_same_response_no_send(client, captured_email):
    unknown = client.post("/auth/resend-verification", json={"email": "ghost@example.com"})
    assert unknown.status_code == 200
    assert "unverified account" in unknown.json()["detail"]
    assert len(captured_email) == 0


def test_resend_verified_account_sends_nothing(client, seller, seller_payload, captured_email):
    response = client.post(
        "/auth/resend-verification", json={"email": seller_payload["email"]}
    )
    assert response.status_code == 200
    assert len(captured_email) == 0  # verified accounts never get re-spammed


def test_resend_unverified_account_sends_new_link(client, seller_payload, captured_email):
    signup_raw(client, seller_payload)

    response = client.post(
        "/auth/resend-verification", json={"email": seller_payload["email"]}
    )
    assert response.status_code == 200

    # Welcome email + the resent one — both carry a working link
    assert len(captured_email) == 2
    resent_token = extract_token(captured_email[1]["body"])
    assert client.get(f"/auth/verify-email?token={resent_token}").status_code == 200
    assert login(client, seller_payload["email"], seller_payload["password"]).status_code == 200


def test_resend_requires_valid_email(client):
    response = client.post("/auth/resend-verification", json={"email": "not-an-email"})
    assert response.status_code == 422
