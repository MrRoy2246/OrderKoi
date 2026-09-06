"""Password hashing and JWT token utilities.

- Passwords: bcrypt (industry standard, salted per-password)
- Tokens: PyJWT HS256 with expiry
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

settings = get_settings()


# ---------- Passwords ----------

def hash_password(plain: str) -> str:
    """Hash a plain-text password with a random salt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plain-text password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Corrupted/invalid stored hash — treat as wrong password
        return False


# ---------- JWT tokens ----------

def create_access_token(subject: str | int) -> str:
    """Create a signed access token for the given seller id."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    # iat (issued-at) lets the server reject tokens minted before a
    # password reset — see Seller.token_invalid_before
    payload = {"sub": str(subject), "iat": now, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the seller id from a valid token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if subject is None:
        return None

    try:
        return int(subject)
    except (TypeError, ValueError):
        return None


def token_issued_at(token: str) -> datetime | None:
    """When this token was minted (aware UTC), or None if unreadable.

    Used together with Seller.token_invalid_before: tokens issued
    before that moment are considered stolen-and-reset and rejected.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    iat = payload.get("iat")
    if iat is None:
        # Tokens minted before the iat claim existed can't be judged —
        # treat them as oldest-possible so a reset still rejects them
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(iat, tz=timezone.utc)
