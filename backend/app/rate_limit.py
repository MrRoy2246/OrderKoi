"""Simple in-memory sliding-window rate limiter (per client IP).

Guards the endpoints most exposed to abuse:
- /auth/login    — brute-force password guessing
- /auth/signup   — automated account creation
- /track/…       — tracking code enumeration
- /public/…      — order-form spam (submissions are extra tight: they
                  burn the seller's free-plan quota)

Single-process only (fine for this deployment stage); a Redis-backed
limiter is the natural upgrade when we scale out.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

# (path prefix, HTTP method (None = any), max requests, window in seconds)
RULES: list[tuple[str, str | None, int, float]] = [
    ("/auth/login", None, 10, 60),
    ("/auth/signup", None, 5, 60),
    ("/auth/forgot-password", None, 5, 60),  # prevents email bombing
    ("/track/", None, 60, 60),
    # Every form submission burns the seller's free-plan quota and
    # triggers a notification email — keep submissions tight. Scoped
    # to POST so loading the form (GET) isn't caught by it.
    ("/public/stores/", "POST", 10, 60),
    ("/public/", None, 30, 60),  # form loads / store lookups
]


class SlidingWindowLimiter:
    """Allows at most `limit` hits per `window` per key."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque] = defaultdict(deque)
        self._ops_since_prune = 0

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]

        # Drop timestamps that fell out of the window
        while hits and now - hits[0] > self.window:
            hits.popleft()

        if len(hits) >= self.limit:
            return False

        hits.append(now)
        self._maybe_prune()
        return True

    def _maybe_prune(self) -> None:
        """Occasionally drop empty keys so memory doesn't grow forever."""
        self._ops_since_prune += 1
        if self._ops_since_prune < 1000:
            return
        self._ops_since_prune = 0
        for key in list(self._hits.keys()):
            if not self._hits[key]:
                del self._hits[key]


_limiters = {
    prefix: SlidingWindowLimiter(limit, window)
    for prefix, _method, limit, window in RULES
}
_lock = threading.Lock()


def enforce_rate_limits(request: Request) -> JSONResponse | None:
    """Check request against all matching rules.

    Returns a 429 JSONResponse when limited, or None when allowed.
    """
    path = request.url.path
    method = request.method.upper()
    client_ip = request.client.host if request.client else "unknown"

    for prefix, rule_method, _limit, window in RULES:
        if not path.startswith(prefix):
            continue
        if rule_method is not None and method != rule_method:
            continue
        key = f"{prefix}:{client_ip}"
        with _lock:
            allowed = _limiters[prefix].allow(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please wait a minute and try again."
                },
                headers={"Retry-After": str(int(window))},
            )
    return None
