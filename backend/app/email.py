"""Email sending.

Development: SMTP not configured — emails are printed to the server log
(the "console backend"). Production: set SMTP_* variables in .env and
real email is sent over TLS.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("orderkoi.email")

settings = get_settings()


def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Never raises — email problems must not
    break the request that triggered them."""
    if not settings.smtp_host:
        logger.info(
            "EMAIL (console backend)\n  To: %s\n  Subject: %s\n  Body:\n%s", to, subject, body
        )
        return

    try:
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

        logger.info("Email sent to %s: %s", to, subject)
    except Exception:  # noqa: BLE001 — logged, never propagated
        logger.exception("Failed to send email to %s", to)
