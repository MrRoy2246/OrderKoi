"""Rate limiter unit tests (the limiter itself, not the HTTP layer)."""

from app.rate_limit import SlidingWindowLimiter


def test_allows_up_to_limit():
    limiter = SlidingWindowLimiter(limit=3, window=60)
    assert limiter.allow("ip-1") is True
    assert limiter.allow("ip-1") is True
    assert limiter.allow("ip-1") is True
    assert limiter.allow("ip-1") is False  # over the limit


def test_keys_are_independent():
    limiter = SlidingWindowLimiter(limit=1, window=60)
    assert limiter.allow("ip-1") is True
    assert limiter.allow("ip-2") is True  # different IP, own budget
    assert limiter.allow("ip-1") is False
    assert limiter.allow("ip-2") is False


def test_window_expires(monkeypatch):
    limiter = SlidingWindowLimiter(limit=1, window=10)

    now = [1000.0]
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: now[0])

    assert limiter.allow("ip-1") is True
    assert limiter.allow("ip-1") is False

    now[0] += 11  # past the window — budget is fresh again
    assert limiter.allow("ip-1") is True


def test_resend_verification_has_a_rule():
    """Resend burns real SMTP quota per request — it needs its own
    guard like forgot-password, not the global default."""
    from app.rate_limit import RULES

    rule = next(r for r in RULES if r[0] == "/auth/resend-verification")
    _, method, limit, window = rule
    assert method in (None, "POST")  # None = any method — fine for a POST-only route
    assert limit <= 10
    assert window <= 300


def test_public_submission_limit_is_tight_and_post_scoped():
    """Form submissions burn the seller's free-plan quota, so they get
    a tight per-IP limit — but only POSTs. Loading the form (GET) must
    not be caught by it (audit fix #8)."""
    from fastapi import Request

    from app.rate_limit import RULES, enforce_rate_limits

    prefix, method, limit, window = next(r for r in RULES if r[0] == "/public/stores/")
    assert method == "POST"
    assert limit <= 10  # tight enough to slow quota-burning abuse
    assert window <= 60

    def make_request(http_method: str) -> Request:
        scope = {
            "type": "http",
            "method": http_method,
            "path": f"{prefix}some-store/orders",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
            "root_path": "",
            "client": ("203.0.113.77", 11111),  # unique IP: no budget shared with other tests
        }
        return Request(scope)

    # `limit` submissions pass, the next is refused with Retry-After
    for _ in range(limit):
        assert enforce_rate_limits(make_request("POST")) is None
    response = enforce_rate_limits(make_request("POST"))
    assert response is not None
    assert response.status_code == 429
    assert response.headers["retry-after"] == str(int(window))

    # GETs on the same path are unaffected by the submission rule
    for _ in range(5):
        assert enforce_rate_limits(make_request("GET")) is None


# ---------- HTTP-level behaviour of the limiter ----------

def _make_request(http_method: str, path: str, ip: str = "203.0.113.99"):
    from fastapi import Request

    return Request(
        {
            "type": "http",
            "method": http_method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
            "root_path": "",
            "client": (ip, 11111),
        }
    )


def _reset_limiters():
    from app import rate_limit

    for limiter in rate_limit._limiters.values():
        limiter._hits.clear()


def test_rate_limited_response_carries_cors_headers(client, monkeypatch):
    """A browser must be able to READ the 429.

    The limiter short-circuits inside a middleware, and a middleware
    that returns without calling `call_next` only inherits headers from
    the layers OUTSIDE it. With CORS registered anywhere but outermost,
    a rate-limited browser request came back with no
    Access-Control-Allow-Origin — so the frontend reported a CORS
    failure instead of "you're going too fast", and could not read
    Retry-After either.
    """
    from app.main import settings

    monkeypatch.setattr(settings, "environment", "development")
    origin = settings.cors_origins[0]

    try:
        last = None
        # A DIFFERENT email each attempt: this must trip the per-IP
        # limiter, not the per-account lockout. The lockout 429s from
        # inside the route, where CORS headers are applied anyway — the
        # test would pass for the wrong reason.
        for index in range(settings.rate_limit_login_max + 1):
            last = client.post(
                "/auth/login",
                json={"email": f"nobody-{index}@example.com", "password": "wrongpass123"},
                headers={"Origin": origin},
            )

        assert last.status_code == 429
        assert last.headers.get("access-control-allow-origin") == origin
        assert last.headers.get("retry-after") == str(
            int(settings.rate_limit_login_window)
        )
    finally:
        # Never leak an exhausted budget into another test
        _reset_limiters()


def test_rate_limiting_can_be_switched_off(monkeypatch):
    """RATE_LIMIT_ENABLED=false — for load testing, never production."""
    from app import rate_limit

    monkeypatch.setattr(rate_limit.settings, "rate_limit_enabled", False)
    try:
        login_limit = next(r[2] for r in rate_limit.RULES if r[0] == "/auth/login")
        # Well past the budget — every request is allowed anyway
        for _ in range(login_limit * 3):
            assert rate_limit.enforce_rate_limits(
                _make_request("POST", "/auth/login")
            ) is None
    finally:
        _reset_limiters()
