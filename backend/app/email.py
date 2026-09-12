"""Email sending.

Development: SMTP not configured — emails are printed to the server log
(the "console backend"). Production: set SMTP_* variables in .env and
real email is sent over TLS.

Delivery happens on a small fixed worker pool: callers (API request
handlers) hand the message off and return immediately — a slow or hung
SMTP server must never add latency to an API response, least of all
the public order form's. A bounded pool (not a thread per send) keeps
a traffic burst from spawning unbounded threads and SMTP connections;
surplus messages wait their turn in the pool's queue. Each send
retries a few times with growing backoff; a final failure is logged
loudly (there is no dead-letter queue at this stage — the log is the
operator's signal).
"""

import logging
import smtplib
import time
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("orderkoi.email")

settings = get_settings()

# Attempts and delays for a background send. Gmail occasionally has a
# slow moment or drops a connection — a short retry covers the vast
# majority of transient failures without delaying "giving up" much.
SEND_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (2, 10)  # before attempt 2 and 3

# Fixed number of concurrent SMTP senders. 4 spreads retries across
# the pool without hammering the relay; queued messages are tiny, so a
# burst just builds a short in-memory queue instead of a thread bomb.
EMAIL_WORKERS = 4

# Created lazily so importing this module never spins up threads (the
# console backend, tests, and scripts don't need a pool at all).
_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=EMAIL_WORKERS, thread_name_prefix="orderkoi-email"
        )
    return _executor


def _send_now(to: str, subject: str, body: str) -> None:
    """Deliver one email over SMTP (no retry, may raise)."""
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


def _deliver_with_retry(to: str, subject: str, body: str) -> None:
    """Try SEND_ATTEMPTS times with backoff; log loudly on final failure."""
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            _send_now(to, subject, body)
            if attempt > 1:
                logger.info("Email to %s succeeded on attempt %d: %s", to, attempt, subject)
            else:
                logger.info("Email sent to %s: %s", to, subject)
            return
        except Exception:  # noqa: BLE001 — retried, then logged, never propagated
            if attempt == SEND_ATTEMPTS:
                logger.exception(
                    "EMAIL DELIVERY FAILED after %d attempts — to=%s subject=%s",
                    SEND_ATTEMPTS, to, subject,
                )
                return
            delay = RETRY_DELAYS_SECONDS[attempt - 1]
            logger.warning(
                "Email to %s failed on attempt %d/%d, retrying in %ds",
                to, attempt, SEND_ATTEMPTS, delay,
            )
            time.sleep(delay)


def send_email(to: str, subject: str, body: str) -> None:
    """Queue an email for delivery. Never raises — email problems must
    not break the request that triggered them, and must not delay it
    either: real SMTP runs on the fixed worker pool; the console
    backend (development, no SMTP_HOST) logs inline so dev output
    stays ordered.
    """
    if not settings.smtp_host:
        logger.info(
            "EMAIL (console backend)\n  To: %s\n  Subject: %s\n  Body:\n%s", to, subject, body
        )
        return

    _get_executor().submit(_deliver_with_retry, to, subject, body)
