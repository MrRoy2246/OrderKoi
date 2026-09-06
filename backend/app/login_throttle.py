"""Per-account login throttling — companion to the per-IP rate limiter.

The HTTP rate limiter (app/rate_limit.py) caps login attempts per IP;
this module caps them per *account*, so an attacker rotating IPs still
can't grind one victim's password forever.

Rules: 5 failed attempts within 15 minutes lock the account for
15 minutes (only wrong-password failures count — a failed attempt on a
nonexistent email throttles that address the same way, so behaviour
never reveals whether an account exists). A successful login clears
the counter.

Single-process, in-memory — same deployment story as the rate limiter
(Redis is the scale-out upgrade, applied to both together).
"""

import threading
import time
from collections import defaultdict, deque

# Failures before lockout, and how long things are remembered
MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 15 * 60  # failures older than this don't count
LOCKOUT_SECONDS = 15 * 60  # how long the account stays locked

_lock = threading.Lock()
# email -> timestamps (monotonic) of recent failed attempts
_failures: dict[str, deque] = defaultdict(deque)
# email -> monotonic time when its lockout ends (absent = not locked)
_locked_until: dict[str, float] = {}


def _prune(now: float, email: str) -> None:
    """Drop expired failures for one address (caller holds the lock)."""
    failures = _failures[email]
    while failures and now - failures[0] > FAILURE_WINDOW_SECONDS:
        failures.popleft()
    if not failures:
        _failures.pop(email, None)


def lockout_remaining(email: str) -> float | None:
    """Seconds the account is still locked for, or None if it's not.

    Also opportunistically cleans up the lock once it expires.
    """
    key = email.strip().lower()
    now = time.monotonic()
    with _lock:
        until = _locked_until.get(key)
        if until is None:
            return None
        if now >= until:
            del _locked_until[key]
            _failures.pop(key, None)
            return None
        return until - now


def record_failure(email: str) -> None:
    """Count one failed attempt; lock the account at the threshold."""
    key = email.strip().lower()
    now = time.monotonic()
    with _lock:
        _prune(now, key)
        _failures[key].append(now)
        if len(_failures[key]) >= MAX_FAILURES:
            _locked_until[key] = now + LOCKOUT_SECONDS
            _failures.pop(key, None)


def clear(email: str) -> None:
    """A successful login forgives everything."""
    key = email.strip().lower()
    with _lock:
        _failures.pop(key, None)
        _locked_until.pop(key, None)
