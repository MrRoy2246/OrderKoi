"""Self-service password change (POST /auth/change-password).

The security-relevant half of this endpoint is the session handling:
a password change is how someone evicts whoever else has their
password, so every previously issued token has to die — while the
device that made the change stays signed in, or the feature punishes
the person using it.
"""

import pytest


@pytest.fixture
def captured_email(monkeypatch):
    """Capture the security notice instead of sending it."""
    sent = []

    def fake_send(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr("app.routes.auth.send_email", fake_send)
    return sent


def change(client, headers, current, new):
    return client.post(
        "/auth/change-password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )


def login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


# ---------- the happy path ----------

def test_changing_the_password_returns_a_usable_token(client, seller, auth_headers, seller_payload):
    response = change(client, auth_headers, seller_payload["password"], "brand-new-pass-1")
    assert response.status_code == 200, response.text

    new_token = response.json()["access_token"]
    # The reissued token works straight away — the device that made the
    # change must not be signed out by its own password change.
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200


def test_the_new_password_is_the_one_that_logs_in(
    client, seller, auth_headers, seller_payload
):
    change(client, auth_headers, seller_payload["password"], "brand-new-pass-1")

    assert login(client, seller_payload["email"], "brand-new-pass-1").status_code == 200
    assert login(client, seller_payload["email"], seller_payload["password"]).status_code == 401


def test_every_older_session_is_signed_out(client, seller, auth_headers, seller_payload):
    """The whole point: whoever else is holding a token loses it.

    Note what this implies — the token that *made* the change dies too,
    since it was minted before the cut-off like any other. That is why
    the endpoint returns a replacement: without storing it the caller
    would sign themselves out, so the frontend has to keep the new one.
    """
    other_device = login(client, seller_payload["email"], seller_payload["password"]).json()
    other_headers = {"Authorization": f"Bearer {other_device['access_token']}"}
    assert client.get("/auth/me", headers=other_headers).status_code == 200

    response = change(client, auth_headers, seller_payload["password"], "brand-new-pass-1")

    assert client.get("/auth/me", headers=other_headers).status_code == 401
    # The replacement is the one live session
    reissued = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/auth/me", headers=reissued).status_code == 200


def test_a_security_notice_goes_out(client, seller, auth_headers, seller_payload, captured_email):
    """Sent even though the owner is the one who did it — the case that
    matters is the one where they didn't."""
    change(client, auth_headers, seller_payload["password"], "brand-new-pass-1")

    assert len(captured_email) == 1
    notice = captured_email[0]
    assert notice["to"] == seller_payload["email"]
    assert "password was changed" in notice["subject"].lower()
    assert "wasn't you" in notice["body"]


# ---------- refusals ----------

def test_a_wrong_current_password_is_refused(client, seller, auth_headers, seller_payload):
    response = change(client, auth_headers, "not-my-password", "brand-new-pass-1")
    # 400 and not 401: the client treats an unexpected 401 as an expired
    # session and signs the user out, so a form error would throw them
    # out of the page they are trying to use.
    assert response.status_code == 400
    assert "current password" in response.json()["detail"].lower()


def test_a_wrong_current_password_changes_nothing(
    client, seller, auth_headers, seller_payload, captured_email
):
    change(client, auth_headers, "not-my-password", "brand-new-pass-1")

    assert login(client, seller_payload["email"], seller_payload["password"]).status_code == 200
    assert captured_email == [], "no security notice for a failed attempt"


def test_the_same_password_is_refused(client, seller, auth_headers, seller_payload):
    """Otherwise the seller "changes" their password, and nothing
    changes — a security action that silently wasn't one."""
    response = change(client, auth_headers, seller_payload["password"], seller_payload["password"])
    assert response.status_code == 400
    assert "different" in response.json()["detail"].lower()


def test_a_short_new_password_is_refused(client, seller, auth_headers, seller_payload):
    response = change(client, auth_headers, seller_payload["password"], "short")
    assert response.status_code == 422


def test_signing_out_is_required(client, seller, seller_payload):
    """No token, no password change — otherwise anyone who guessed a
    password they don't need a session for anyway."""
    response = client.post(
        "/auth/change-password",
        json={"current_password": seller_payload["password"], "new_password": "brand-new-pass-1"},
    )
    assert response.status_code == 401


def test_repeated_guesses_lock_the_account(
    client, seller, auth_headers, seller_payload
):
    """A stolen token plus a password guess is the attack this closes:
    same throttle as login, so 5 wrong tries freeze the account."""
    from app.config import get_settings

    attempts = get_settings().login_max_failures
    for _ in range(attempts):
        change(client, auth_headers, "guess", "brand-new-pass-1")

    locked = change(client, auth_headers, seller_payload["password"], "brand-new-pass-1")
    assert locked.status_code == 429
    # And the lock is the same one login uses — not a second, looser door
    assert login(client, seller_payload["email"], seller_payload["password"]).status_code == 429


def test_a_successful_change_clears_the_failure_count(
    client, seller, auth_headers, seller_payload
):
    """A seller who fumbles their current password twice and then gets
    it right must not be two thirds of the way to a lockout."""
    change(client, auth_headers, "wrong-1", "brand-new-pass-1")
    change(client, auth_headers, "wrong-2", "brand-new-pass-1")
    assert change(
        client, auth_headers, seller_payload["password"], "brand-new-pass-1"
    ).status_code == 200

    from app import login_throttle

    assert login_throttle.lockout_remaining(seller_payload["email"]) is None
