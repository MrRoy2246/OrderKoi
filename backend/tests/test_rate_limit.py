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
