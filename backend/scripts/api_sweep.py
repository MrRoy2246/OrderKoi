#!/usr/bin/env python
"""Live API sweep — every route, against a running dev server.

Why this exists next to the pytest suite
----------------------------------------
The suite runs in-process, on a throwaway database, with the email
backend forced to "console". It proves the *code* is right. It cannot
prove the *deployment* is: that uvicorn really serves these routes,
that the real dev database accepts the writes, and that an email
actually leaves the machine over SMTP. That is what this script
checks — over HTTP, with backend/.env exactly as it stands.

Usage (with the dev servers up — see docs/BACKEND_GUIDE.md):

    cd backend
    ./venv/Scripts/python.exe -m scripts.api_sweep

Every failure prints the response *and* the server log written during
that call, with the ``file:line`` from the log format — so a red X here
points straight at the code, not at a symptom.

What it creates, and what it leaves behind
------------------------------------------
One seller account, whose signup really sends a verification email
(that is the point of it), and a couple of orders under it. The orders
are deleted on the way out. The account is deliberately left in place
— it is the one to open the inbox for. Pass ``--delete-account`` to
remove it too.

Rate limits are real here: the dev server enforces them (10 logins,
5 signups, 5 password resets per minute per IP). The sweep spaces its
state-changing calls and backs off once on a 429, but two sweeps
inside one minute will still collide — wait it out rather than
loosening the limit.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

BASE_URL = os.environ.get("SWEEP_BASE_URL", "http://localhost:8000")
DEFAULT_LOG = Path(
    os.environ.get("SWEEP_BACKEND_LOG", "")
    or Path(os.environ.get("TEMP", "/tmp")) / "orderkoi-dev" / "backend.log"
)

# The admin account every environment is expected to have (see
# docs/DEPLOYMENT.md — created with `python -m scripts.create_admin`).
ADMIN_EMAIL = os.environ.get("SWEEP_ADMIN_EMAIL", "abin@test.com")
ADMIN_PASSWORD = os.environ.get("SWEEP_ADMIN_PASSWORD", "secretpass123")

# Matches a traceback frame, so a failed call can name the exact file
# and line rather than leaving the reader to grep the source.
FRAME = re.compile(r'File "([^"]+\.py)", line (\d+)')

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


class Sweep:
    """Runs ordered checks and reports each one, with the server's own
    account of anything that went wrong."""

    def __init__(self, base_url: str, log_path: Path, verbose: bool) -> None:
        self.base = base_url
        self.log_path = log_path
        self.verbose = verbose
        self.client = httpx.Client(base_url=base_url, timeout=30.0, follow_redirects=False)
        self.passed = 0
        self.failures: list[str] = []
        self.section = ""
        self._offset = self._log_size()

    # ---------- output ----------

    def heading(self, title: str) -> None:
        self.section = title
        print(f"\n{DIM}── {title} {'─' * max(0, 58 - len(title))}{RESET}")

    def ok(self, label: str, detail: str = "") -> None:
        self.passed += 1
        print(f"  {GREEN}PASS{RESET} {label}{f'  {DIM}{detail}{RESET}' if detail else ''}")

    def fail(self, label: str, detail: str) -> None:
        self.failures.append(f"[{self.section}] {label}: {detail}")
        print(f"  {RED}FAIL{RESET} {label}")
        print(f"       {RED}{detail}{RESET}")
        for line in self._log_since().splitlines()[-14:]:
            print(f"       {DIM}{line}{RESET}")

    # ---------- server log ----------

    def _log_size(self) -> int:
        try:
            return self.log_path.stat().st_size
        except OSError:
            return 0

    def _log_since(self) -> str:
        """What the server wrote since the last checkpoint, cleaned up."""
        if not self.log_path.exists():
            return f"(no server log at {self.log_path})"
        with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self._offset)
            text_block = handle.read()
        lines = [line.rstrip() for line in text_block.splitlines() if line.strip()]
        return "\n".join(lines) or "(the server logged nothing during this call)"

    def checkpoint(self) -> None:
        self._offset = self._log_size()

    def wait_for_log(self, pattern: str, timeout: float = 30.0) -> str | None:
        """Wait for a line the server prints asynchronously — an email is
        handed to a background thread, so its log line lands after the
        response the caller got."""
        deadline = time.monotonic() + timeout
        seen = self._offset
        while time.monotonic() < deadline:
            if self.log_path.exists():
                with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(seen)
                    chunk = handle.read()
                for line in chunk.splitlines():
                    if pattern in line:
                        return line.strip()
            time.sleep(0.5)
        return None

    # ---------- requests ----------

    def call(
        self,
        label: str,
        method: str,
        path: str,
        *,
        expect: int | set[int],
        token: str | None = None,
        json: dict | None = None,
        params: dict | None = None,
        extra_headers: dict | None = None,
        retry_on_429: bool = True,
    ) -> httpx.Response | None:
        """One request, one check. Returns None when the call failed, so
        callers can stop before dereferencing a body that isn't there."""
        expected = expect if isinstance(expect, set) else {expect}
        headers = dict(extra_headers or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self.checkpoint()
        try:
            response = self.client.request(
                method, path, json=json, params=params, headers=headers
            )
        except httpx.HTTPError as exc:
            self.fail(label, f"{method} {path} — could not reach the server: {exc!r}")
            return None

        # The dev server rate-limits by IP; a burst can trip it. One
        # wait is enough to tell a real failure from a busy one.
        if response.status_code == 429 and retry_on_429:
            retry_after = int(response.headers.get("Retry-After", "10") or 10)
            print(f"  {YELLOW}WAIT{RESET} {label} — rate limited, retrying in {retry_after}s")
            time.sleep(min(retry_after, 65) + 1)
            return self.call(
                label,
                method,
                path,
                expect=expect,
                token=token,
                json=json,
                params=params,
                extra_headers=extra_headers,
                retry_on_429=False,
            )

        if response.status_code not in expected:
            wanted = "/".join(str(code) for code in sorted(expected))
            body = response.text[:400].replace("\n", " ")
            self.fail(
                label,
                f"{method} {path} → {response.status_code} (wanted {wanted})  {body}",
            )
            return None

        suffix = f"  {DIM}{response.status_code}{RESET}"
        print(f"  {GREEN}PASS{RESET} {label}{suffix}")
        self.passed += 1
        return response

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        """An assertion that isn't about a status code."""
        if condition:
            self.ok(label, detail)
            return True
        self.fail(label, detail or "condition not met")
        return False

    # ---------- database ----------

    def scoped(self, email: str) -> int | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT id FROM sellers WHERE email = :email"), {"email": email}
            ).first()
        return row[0] if row else None

    def plant_token(self, table: str, seller_id: int, minutes: int = 30) -> str:
        """Insert a token whose plaintext we know.

        The server stores only the SHA-256, so a token that arrives by
        email cannot be read back out of the database — which is the
        point of hashing it, and also means a live sweep has to mint
        one the same way the server would. Same table, same hash, same
        expiry column: the endpoint under test cannot tell the
        difference.
        """
        token = secrets.token_urlsafe(32)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {table} (seller_id, token_hash, expires_at) "  # noqa: S608
                    "VALUES (:seller_id, :token_hash, :expires_at)"
                ),
                {
                    "seller_id": seller_id,
                    "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                    "expires_at": datetime.now(timezone.utc) + timedelta(minutes=minutes),
                },
            )
        return token

    # ---------- lifecycle ----------

    def __enter__(self) -> Sweep:
        self.engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        return self

    def __exit__(self, *_exc) -> None:
        self.client.close()
        self.engine.dispose()

    def summary(self) -> int:
        total = self.passed + len(self.failures)
        print(f"\n{'=' * 62}")
        if not self.failures:
            print(f"{GREEN}{self.passed}/{total} checks passed{RESET}")
            return 0
        print(f"{RED}{len(self.failures)} of {total} checks FAILED{RESET}\n")
        for failure in self.failures:
            print(f"  {RED}✗{RESET} {failure}\n")
        return 1


def run(sweep: Sweep, *, delete_account: bool) -> None:
    """The sweep itself, in the order a real seller would hit it."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # Override with SWEEP_EMAIL. The default is a deliberately
    # undeliverable address: it still proves the server authenticates
    # and hands the message to SMTP, but a real relay may refuse it,
    # and *that* refusal is worth seeing too.
    email = os.environ.get("SWEEP_EMAIL") or f"sweep+{stamp}@example.com"
    password = "sweep-pass-12345"
    rotated = "sweep-pass-67890"

    # Re-running is the normal case for a sweep, and the second run
    # must behave exactly like the first — so start from a clean slate
    # for the one address the operator nominated, and nothing else.
    # Every foreign key onto sellers is ON DELETE CASCADE, so this also
    # clears that account's orders, tokens and plan history.
    with sweep.engine.begin() as conn:
        conn.execute(text("DELETE FROM sellers WHERE email = :email"), {"email": email})

    sweep.heading("system")
    health = sweep.call("GET /health", "GET", "/health", expect=200)
    if health:
        sweep.check(
            "the hardening headers ride on every response",
            health.headers.get("x-content-type-options") == "nosniff",
            f"X-Content-Type-Options={health.headers.get('x-content-type-options')!r}",
        )
    sweep.call("GET /ready (a real SELECT 1)", "GET", "/ready", expect=200)
    pricing = sweep.call(
        "GET /public/stores/pricing (public config)", "GET", "/public/stores/pricing", expect=200
    )
    if pricing:
        data = pricing.json()
        sweep.check(
            "all three Pro durations are priced",
            [entry["months"] for entry in data["pro"]] == [1, 6, 12],
            str([entry["months"] for entry in data["pro"]]),
        )
        sweep.check(
            "bKash details and support contact come through env",
            bool(data["bkash_number"]) and "@" in data["support_email"],
            f"bkash={data['bkash_number']} support={data['support_email']}",
        )

    # ---------- signup, and the email it really sends ----------
    sweep.heading("signup + a real email")
    payload = {
        "email": email,
        "password": password,
        "store_name": f"Sweep Store {stamp}",
        "phone": "01712345678",
    }
    signup = sweep.call("POST /auth/signup", "POST", "/auth/signup", expect=201, json=payload)
    sweep.call(
        "POST /auth/signup — duplicate email refused",
        "POST",
        "/auth/signup",
        expect=409,
        json=payload,
    )
    sweep.call(
        "POST /auth/signup — a short password refused",
        "POST",
        "/auth/signup",
        expect=422,
        json={**payload, "email": f"short+{stamp}@example.com", "password": "short1"},
    )

    # The send happens on a background thread, so its log line lands
    # after the 201 the caller already has.
    line = sweep.wait_for_log(f"Email sent to {email}", timeout=45)
    if line:
        sweep.ok("the verification email really left over SMTP", line.split(" ", 2)[-1][:90])
    else:
        sweep.fail(
            "the verification email really left over SMTP",
            f"no 'Email sent to {email}' within 45s — the log below says why",
        )

    sweep.call(
        "POST /auth/login — refused until the address is verified",
        "POST",
        "/auth/login",
        expect=403,
        json={"email": email, "password": password},
    )

    # ---------- verification ----------
    sweep.heading("email verification")
    seller_id = sweep.scoped(email)
    if not sweep.check("the seller row is in the database", seller_id is not None, email):
        return

    token = sweep.plant_token("email_verification_tokens", seller_id)
    sweep.call(
        "GET /auth/verify-email — the link works",
        "GET",
        "/auth/verify-email",
        expect=200,
        params={"token": token},
    )
    replay = sweep.call(
        "GET /auth/verify-email — a refresh is idempotent, not an error",
        "GET",
        "/auth/verify-email",
        expect=200,
        params={"token": token},
    )
    if replay:
        sweep.check(
            "…and it says the account was already verified",
            "already verified" in str(replay.json().get("detail", "")),
            replay.json().get("detail", ""),
        )
    sweep.call(
        "GET /auth/verify-email — a garbage token refused",
        "GET",
        "/auth/verify-email",
        expect=400,
        params={"token": "x" * 43},
    )
    sweep.call(
        "GET /auth/verify-email — no token at all refused",
        "GET",
        "/auth/verify-email",
        expect=422,
    )
    sweep.call(
        "POST /auth/resend-verification",
        "POST",
        "/auth/resend-verification",
        expect=200,
        json={"email": email},
    )
    sweep.wait_for_log(f"Email sent to {email}", timeout=45)

    # ---------- auth ----------
    sweep.heading("sessions")
    login = sweep.call(
        "POST /auth/login — a verified account gets a token",
        "POST",
        "/auth/login",
        expect=200,
        json={"email": email, "password": password},
    )
    if not login:
        return
    token_current = login.json()["access_token"]

    me = sweep.call("GET /auth/me", "GET", "/auth/me", expect=200, token=token_current)
    slug = me.json()["store_slug"] if me else None
    if me:
        sweep.check(
            "the account is the one that signed up, and verified",
            me.json()["email"] == email and me.json()["email_verified"] is True,
            f"plan={me.json()['plan']} slug={slug}",
        )
    sweep.call(
        "PATCH /auth/me — store details editable",
        "PATCH",
        "/auth/me",
        expect=200,
        token=token_current,
        json={"store_name": f"Sweep Store {stamp} (edited)", "phone": "01812345678"},
    )
    sweep.call("GET /auth/me — no token refused", "GET", "/auth/me", expect=401)
    sweep.call(
        "GET /auth/me — a forged token refused",
        "GET",
        "/auth/me",
        expect=401,
        token="not.a.real.jwt",
    )

    # ---------- password reset ----------
    sweep.heading("password reset (forgotten password)")
    sweep.call(
        "POST /auth/forgot-password",
        "POST",
        "/auth/forgot-password",
        expect=200,
        json={"email": email},
    )
    sweep.wait_for_log(f"Email sent to {email}", timeout=45)
    sweep.call(
        "POST /auth/forgot-password — an unknown address looks the same (no user enumeration)",
        "POST",
        "/auth/forgot-password",
        expect=200,
        json={"email": f"nobody+{stamp}@example.com"},
    )

    reset_token = sweep.plant_token("password_reset_tokens", seller_id)
    sweep.call(
        "POST /auth/reset-password",
        "POST",
        "/auth/reset-password",
        expect=200,
        json={"token": reset_token, "new_password": rotated},
    )
    sweep.call(
        "POST /auth/login — the reset password works",
        "POST",
        "/auth/login",
        expect=200,
        json={"email": email, "password": rotated},
    )
    sweep.call(
        "GET /auth/me — the token from before the reset is dead",
        "GET",
        "/auth/me",
        expect=401,
        token=token_current,
    )
    sweep.call(
        "POST /auth/reset-password — the reset link is single-use",
        "POST",
        "/auth/reset-password",
        expect=400,
        json={"token": reset_token, "new_password": "another-pass-12345"},
    )

    # ---------- change password while signed in ----------
    sweep.heading("change password while signed in")
    relogin = sweep.call(
        "POST /auth/login (with the reset password)",
        "POST",
        "/auth/login",
        expect=200,
        json={"email": email, "password": rotated},
    )
    if not relogin:
        return
    token_current = relogin.json()["access_token"]

    sweep.call(
        "POST /auth/change-password — a wrong current password refused",
        "POST",
        "/auth/change-password",
        expect=400,
        token=token_current,
        json={"current_password": "definitely-not-it", "new_password": "whatever-pass-1"},
    )
    sweep.call(
        "POST /auth/change-password",
        "POST",
        "/auth/change-password",
        expect=200,
        token=token_current,
        json={"current_password": rotated, "new_password": password},
    )
    sweep.wait_for_log(f"Email sent to {email}", timeout=45)
    sweep.call(
        "GET /auth/me — the old token died with the password change",
        "GET",
        "/auth/me",
        expect=401,
        token=token_current,
    )
    moved = sweep.call(
        "POST /auth/login — the new password works",
        "POST",
        "/auth/login",
        expect=200,
        json={"email": email, "password": password},
    )
    if not moved:
        return
    token_current = moved.json()["access_token"]

    # ---------- orders ----------
    sweep.heading("orders (the seller dashboard)")
    order_payload = {
        "customer_name": "Sweep Customer",
        "customer_phone": "01812345678",
        "customer_address": "House 12, Road 5, Dhanmondi, Dhaka",
        "items": [
            {"name": "Cotton T-Shirt", "quantity": 2, "price": 550},
            {"name": "Cap", "quantity": 1, "price": 300},
        ],
        "notes": "Sweep order — safe to delete",
    }
    created = sweep.call(
        "POST /orders",
        "POST",
        "/orders",
        expect=201,
        token=token_current,
        json=order_payload,
    )
    order_id = created.json()["id"] if created else None
    if created:
        sweep.check(
            "the server computed the total (2×550 + 300)",
            float(created.json()["total_price"]) == 1400.0,
            f"total_price={created.json()['total_price']}",
        )
    sweep.call(
        "POST /orders — a negative price refused",
        "POST",
        "/orders",
        expect=422,
        token=token_current,
        json={**order_payload, "items": [{"name": "Bad", "quantity": 1, "price": -5}]},
    )
    listed = sweep.call("GET /orders", "GET", "/orders", expect=200, token=token_current)
    if listed:
        sweep.check(
            "the new order is in the seller's list",
            any(o["id"] == order_id for o in listed.json()["orders"]),
            f"total={listed.json()['total']}",
        )
    sweep.call("GET /orders/stats/summary", "GET", "/orders/stats/summary", expect=200, token=token_current)
    export = sweep.call("GET /orders/export (CSV)", "GET", "/orders/export", expect=200, token=token_current)
    if export:
        sweep.check(
            "the export is really CSV",
            "text/csv" in export.headers.get("content-type", ""),
            export.headers.get("content-type", ""),
        )
    if order_id:
        sweep.call(
            f"GET /orders/{order_id}",
            "GET",
            f"/orders/{order_id}",
            expect=200,
            token=token_current,
        )
        sweep.call(
            "PATCH /orders/{id} — customer details editable",
            "PATCH",
            f"/orders/{order_id}",
            expect=200,
            token=token_current,
            json={"customer_address": "Flat 3B, Gulshan 1, Dhaka"},
        )
        sweep.call(
            "PATCH /orders/{id}/status — placed → shipped refused (no skipping steps)",
            "PATCH",
            f"/orders/{order_id}/status",
            expect=409,
            token=token_current,
            json={"status": "shipped"},
        )
        sweep.call(
            "PATCH /orders/{id}/status — placed → confirmed",
            "PATCH",
            f"/orders/{order_id}/status",
            expect=200,
            token=token_current,
            json={"status": "confirmed"},
        )
        sweep.call(
            "PATCH /orders/{id}/status — confirmed → shipped",
            "PATCH",
            f"/orders/{order_id}/status",
            expect=200,
            token=token_current,
            json={"status": "shipped"},
        )
        sweep.call(
            "PATCH /orders/{id}/status — an invented status refused",
            "PATCH",
            f"/orders/{order_id}/status",
            expect=422,
            token=token_current,
            json={"status": "teleported"},
        )

    # ---------- public storefront + tracking ----------
    sweep.heading("public storefront + customer tracking")
    store = sweep.call(f"GET /public/stores/{slug}", "GET", f"/public/stores/{slug}", expect=200)
    sweep.call(
        "GET /public/stores — an unknown shop is a 404, not a blank page",
        "GET",
        "/public/stores/definitely-not-a-shop",
        expect=404,
    )
    form_payload = {
        "customer_name": "Sweep Walk-in",
        "customer_phone": "01911111111",
        "customer_email": "sweep.customer@example.com",
        "customer_address": "House 9, Road 2, Uttara, Dhaka",
        "items": [{"name": "Panjabi", "quantity": 1, "price": 1200}],
        "notes": "Sweep customer order — safe to delete",
    }
    public_order = sweep.call(
        "POST /public/stores/{slug}/orders — a customer orders without an account",
        "POST",
        f"/public/stores/{slug}/orders",
        expect=201,
        json=form_payload,
    )
    public_code = public_order.json()["tracking_code"] if public_order else None
    if public_order:
        sweep.check(
            "the shop is told about the new order (real email)",
            sweep.wait_for_log("Email sent to", timeout=45) is not None,
            "seller notification",
        )
    sweep.call(
        "POST /public/stores/{slug}/orders — a bad payload refused",
        "POST",
        f"/public/stores/{slug}/orders",
        expect=422,
        json={"customer_name": "X"},
    )
    if public_code:
        tracked = sweep.call(
            f"GET /track/{public_code} (no login needed)",
            "GET",
            f"/track/{public_code}",
            expect=200,
        )
        if tracked:
            sweep.check(
                "tracking names the right shop and the order's real state",
                tracked.json()["store_name"].startswith("Sweep Store")
                and tracked.json()["status"] == "placed",
                f"{tracked.json()['store_name']} / {tracked.json()['status']}",
            )
            sweep.check(
                "tracking never leaks the customer's address or phone",
                "customer_address" not in tracked.json()
                and "customer_phone" not in tracked.json(),
                str(sorted(tracked.json())),
            )
    sweep.call(
        "GET /track — an unknown code is a 404",
        "GET",
        "/track/NOPE123456",
        expect=404,
    )
    if order_id:
        detail = sweep.call(
            "GET /orders/{id} — the seller's own order, with its tracking code",
            "GET",
            f"/orders/{order_id}",
            expect=200,
            token=token_current,
        )
        if detail:
            swept_track = sweep.call(
                "GET /track/{code} — that code tracks the seller's order too",
                "GET",
                f"/track/{detail.json()['tracking_code']}",
                expect=200,
            )
            if swept_track:
                sweep.check(
                    "…and shows the status the seller moved it to",
                    swept_track.json()["status"] == "shipped"
                    and len(swept_track.json()["status_history"]) >= 3,
                    f"status={swept_track.json()['status']} "
                    f"history={len(swept_track.json()['status_history'])} entries",
                )

    # ---------- upgrade to Pro ----------
    sweep.heading("upgrade to Pro (the bKash request flow)")
    upgrade = sweep.call(
        "POST /auth/upgrade-requests",
        "POST",
        "/auth/upgrade-requests",
        expect=201,
        token=token_current,
        json={"months": 1, "payment_reference": f"SWEEP-{stamp}"},
    )
    request_id = upgrade.json()["id"] if upgrade else None
    sweep.call(
        "POST /auth/upgrade-requests — a second pending request refused",
        "POST",
        "/auth/upgrade-requests",
        expect=409,
        token=token_current,
        json={"months": 6},
    )
    sweep.call(
        "POST /auth/upgrade-requests — an off-menu duration refused",
        "POST",
        "/auth/upgrade-requests",
        expect=422,
        token=token_current,
        json={"months": 3},
    )
    history = sweep.call(
        "GET /auth/upgrade-requests", "GET", "/auth/upgrade-requests", expect=200, token=token_current
    )
    if history:
        sweep.check(
            "the request is in the seller's own history as pending",
            any(r["id"] == request_id and r["status"] == "pending" for r in history.json()),
            f"{len(history.json())} entries",
        )
    sweep.call(
        "GET /auth/subscription-history",
        "GET",
        "/auth/subscription-history",
        expect=200,
        token=token_current,
    )

    # ---------- admin ----------
    sweep.heading("admin console")
    admin_login = sweep.call(
        "POST /auth/login — the platform admin",
        "POST",
        "/auth/login",
        expect=200,
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if not admin_login:
        print(f"  {YELLOW}SKIP{RESET} admin checks — could not sign in as {ADMIN_EMAIL}")
        return
    admin = admin_login.json()["access_token"]

    sweep.call(
        "GET /admin/stats with a seller token (403, not 401 — the token is fine)",
        "GET",
        "/admin/stats",
        expect=403,
        token=token_current,
    )
    sweep.call("GET /admin/stats", "GET", "/admin/stats", expect=200, token=admin)
    sellers = sweep.call(
        "GET /admin/sellers (paginated envelope)", "GET", "/admin/sellers", expect=200, token=admin
    )
    if sellers:
        sweep.check(
            "the list is an envelope with a real total",
            "sellers" in sellers.json() and sellers.json()["total"] > 0,
            f"total={sellers.json().get('total')}",
        )
    sweep.call(
        "GET /admin/sellers?search= filters server-side",
        "GET",
        "/admin/sellers",
        expect=200,
        token=admin,
        params={"search": "Sweep Store", "limit": 5},
    )
    stats = sweep.call(
        f"GET /admin/sellers/{seller_id}/stats",
        "GET",
        f"/admin/sellers/{seller_id}/stats",
        expect=200,
        token=admin,
    )
    if stats:
        sweep.check(
            "the shop's stats report the sweep order",
            stats.json().get("total_orders", 0) >= 1,
            f"total_orders={stats.json().get('total_orders')}",
        )
    sweep.call(
        f"GET /admin/sellers/{seller_id}/orders.csv",
        "GET",
        f"/admin/sellers/{seller_id}/orders.csv",
        expect=200,
        token=admin,
    )
    events = sweep.call(
        "GET /admin/subscription-events", "GET", "/admin/subscription-events", expect=200, token=admin
    )
    if events:
        sweep.check(
            "the ledger is a list, and capped rather than unbounded",
            isinstance(events.json(), list) and len(events.json()) <= 200,
            f"{type(events.json()).__name__}, {len(events.json())} rows (server caps at 200)",
        )
    queue = sweep.call(
        "GET /admin/upgrade-requests (the payment queue)",
        "GET",
        "/admin/upgrade-requests",
        expect=200,
        token=admin,
    )
    if queue:
        sweep.check(
            "the sweep's request is waiting in it",
            any(r["id"] == request_id for r in queue.json()["requests"]),
            f"total={queue.json().get('total')}",
        )

    if request_id:
        approved = sweep.call(
            "PATCH /admin/upgrade-requests/{id} — approve activates Pro",
            "PATCH",
            f"/admin/upgrade-requests/{request_id}",
            expect=200,
            token=admin,
            json={"action": "approve"},
        )
        if approved:
            sweep.check(
                "approval sets a real expiry date",
                bool(approved.json().get("plan_expires_at")),
                f"plan_expires_at={approved.json().get('plan_expires_at')}",
            )
        sweep.call(
            "PATCH /admin/upgrade-requests/{id} — approving twice refused",
            "PATCH",
            f"/admin/upgrade-requests/{request_id}",
            expect=409,
            token=admin,
            json={"action": "approve"},
        )
        after = sweep.call(
            "GET /auth/me — the seller is on Pro now",
            "GET",
            "/auth/me",
            expect=200,
            token=token_current,
        )
        if after:
            sweep.check(
                "the plan really flipped",
                after.json()["plan"] == "pro",
                f"plan={after.json()['plan']} expires={after.json().get('plan_expires_at')}",
            )

    manual = sweep.call(
        "PATCH /admin/sellers/{id}/plan — a manual Pro activation (a different path from approval)",
        "PATCH",
        f"/admin/sellers/{seller_id}/plan",
        expect=200,
        token=admin,
        json={"plan": "pro", "months": 1},
    )
    if manual:
        sweep.check(
            "the manual activation sets its own expiry",
            bool(manual.json().get("plan_expires_at")),
            f"plan_expires_at={manual.json().get('plan_expires_at')}",
        )

    # ---------- suspension ----------
    sweep.heading("suspension (the switch that must hold everywhere)")
    sweep.call(
        "PATCH /admin/sellers/{id}/suspension — suspend",
        "PATCH",
        f"/admin/sellers/{seller_id}/suspension",
        expect=200,
        token=admin,
        json={"suspended": True, "reason": "Sweep — safe to reinstate"},
    )
    blocked = sweep.call(
        "POST /auth/login — a suspended seller cannot sign in",
        "POST",
        "/auth/login",
        expect=403,
        json={"email": email, "password": password},
    )
    if blocked:
        sweep.check(
            "…and the refusal is machine-readable (the marker header)",
            blocked.headers.get("x-orderkoi-suspended") == "1",
            f"X-OrderKoi-Suspended={blocked.headers.get('x-orderkoi-suspended')!r}",
        )
    sweep.call(
        "GET /auth/me — the token minted before the suspension is dead too",
        "GET",
        "/auth/me",
        expect=403,
        token=token_current,
    )
    sweep.call(
        "POST /public/stores/{slug}/orders — the shop stops taking orders",
        "POST",
        f"/public/stores/{slug}/orders",
        expect=403,
        json=form_payload,
    )
    listed = sweep.call(
        "GET /admin/sellers — the admin sees who is suspended",
        "GET",
        "/admin/sellers",
        expect=200,
        token=admin,
        params={"search": "Sweep Store", "limit": 5},
    )
    if listed:
        rows = listed.json()["sellers"]
        sweep.check(
            "…with the reason attached",
            bool(rows) and rows[0]["suspended_at"] is not None,
            f"suspended_reason={rows[0].get('suspended_reason') if rows else None}",
        )
    if public_code:
        sweep.call(
            "GET /track — customers of a suspended shop can still track",
            "GET",
            f"/track/{public_code}",
            expect=200,
        )
    sweep.call(
        "PATCH /admin/sellers/{id}/suspension — reinstate",
        "PATCH",
        f"/admin/sellers/{seller_id}/suspension",
        expect=200,
        token=admin,
        json={"suspended": False},
    )
    back = sweep.call(
        "POST /auth/login — reinstated, and signed in again",
        "POST",
        "/auth/login",
        expect=200,
        json={"email": email, "password": password},
    )
    if back:
        token_current = back.json()["access_token"]

    # ---------- cross-tenant isolation ----------
    sweep.heading("cross-tenant isolation")
    other = sweep.call(
        "POST /auth/login — a different seller",
        "POST",
        "/auth/login",
        expect=200,
        json={"email": os.environ.get("SWEEP_OTHER_EMAIL", "test@gmail.com"), "password": os.environ.get("SWEEP_OTHER_PASSWORD", "test123456789")},
    )
    if other and order_id:
        other_token = other.json()["access_token"]
        theirs = sweep.call(
            "GET /orders — their own list",
            "GET",
            "/orders",
            expect=200,
            token=other_token,
            params={"limit": 1},
        )
        if theirs and theirs.json()["orders"]:
            their_order = theirs.json()["orders"][0]["id"]
            sweep.call(
                "GET /orders/{their id} with the sweep seller's token → 404",
                "GET",
                f"/orders/{their_order}",
                expect=404,
                token=token_current,
            )
            sweep.call(
                "DELETE /orders/{their id} with the sweep seller's token → 404",
                "DELETE",
                f"/orders/{their_order}",
                expect=404,
                token=token_current,
            )
    else:
        print(
            f"  {YELLOW}SKIP{RESET} cross-tenant checks — could not sign in as the other seller"
        )

    # ---------- cancel subscription ----------
    sweep.heading("cancel subscription")
    sweep.call(
        "POST /auth/cancel-subscription",
        "POST",
        "/auth/cancel-subscription",
        expect=200,
        token=token_current,
    )
    swept = sweep.call(
        "GET /auth/me — back to the free plan",
        "GET",
        "/auth/me",
        expect=200,
        token=token_current,
    )
    if swept:
        sweep.check("the plan is free again", swept.json()["plan"] == "free", swept.json()["plan"])

    # ---------- cleanup ----------
    sweep.heading("cleanup")
    # An order is only deletable while it is still 'placed' — once it
    # has moved on it is a record, not a draft. So the sweep order
    # (now 'shipped', with a real status history) is left in place as
    # demo data, and a throwaway order is used to exercise DELETE.
    if order_id:
        sweep.call(
            "DELETE /orders/{id} — refused once the order has moved on",
            "DELETE",
            f"/orders/{order_id}",
            expect=409,
            token=token_current,
        )
    throwaway = sweep.call(
        "POST /orders — one more, to delete",
        "POST",
        "/orders",
        expect=201,
        token=token_current,
        json={**order_payload, "notes": "Sweep throwaway — deleted immediately"},
    )
    if throwaway:
        throwaway_id = throwaway.json()["id"]
        sweep.call(
            f"DELETE /orders/{throwaway_id} — a fresh order deletes cleanly",
            "DELETE",
            f"/orders/{throwaway_id}",
            expect=204,
            token=token_current,
        )
        sweep.call(
            f"GET /orders/{throwaway_id} — and it is gone",
            "GET",
            f"/orders/{throwaway_id}",
            expect=404,
            token=token_current,
        )
    if delete_account:
        with sweep.engine.begin() as conn:
            conn.execute(text("DELETE FROM sellers WHERE email = :email"), {"email": email})
        sweep.ok("the sweep account and everything under it removed", email)
    else:
        print(
            f"  {DIM}left behind: {email} (password {password}) — the account to open the\n"
            f"  inbox for, with a shipped order under it. Pass --delete-account to remove.{RESET}"
        )


def main() -> int:
    # A Windows console defaults to cp1252, and this script draws box
    # characters and a ✗. Without this the run dies on the first
    # heading with a UnicodeEncodeError — which is a worse failure than
    # anything it was about to report.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--delete-account", action="store_true")
    args = parser.parse_args()

    with Sweep(args.base_url, args.log, verbose=True) as sweep:
        try:
            sweep.client.get("/health")
        except httpx.HTTPError as exc:
            print(f"{RED}Cannot reach the API at {args.base_url}{RESET}: {exc!r}")
            print("Start it first — see docs/BACKEND_GUIDE.md (uvicorn, no --reload).")
            return 2
        print(f"{DIM}sweeping {args.base_url} — server log {args.log}{RESET}")
        run(sweep, delete_account=args.delete_account)
        return sweep.summary()


if __name__ == "__main__":
    raise SystemExit(main())
