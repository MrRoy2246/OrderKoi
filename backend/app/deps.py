"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Seller
from app.security import decode_access_token, token_issued_at

# Swagger shows a 🔒 Authorize button; the frontend sends
# "Authorization: Bearer <token>"
bearer_scheme = HTTPBearer(auto_error=False)

# Machine-readable marker attached to the "account suspended" 403s, so
# the frontend can tell that case apart from every other 403 (a seller
# hitting an admin route, for one) without string-matching user-facing
# copy that is free to be reworded later. Browsers hide custom response
# headers unless they are exposed — see expose_headers in app/main.py.
SUSPENDED_HEADER = "X-OrderKoi-Suspended"


def suspended_error() -> HTTPException:
    """The 403 a suspended account gets, from both places that raise it.

    Defined once because the message and the marker header have to stay
    in step: this module guards every authenticated route and
    routes/auth.py guards login, and a change to one of them that
    missed the other would show up as a frontend bug.

    403, not 401: the token is perfectly valid — the account is the
    problem. A 401 would make the frontend discard the session and
    bounce to the login page, which reads as "just sign in again and
    it'll work", and it wouldn't.
    """
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This account has been suspended. Contact support if "
        "you believe this is a mistake.",
        headers={SUSPENDED_HEADER: "1"},
    )


def get_current_seller(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Seller:
    """Resolve the logged-in seller from the Authorization header."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide a valid bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    seller_id = decode_access_token(credentials.credentials)
    if seller_id is None:
        raise unauthorized

    seller = db.get(Seller, seller_id)
    if seller is None:
        raise unauthorized

    # A password reset happened after this token was minted — the
    # token is presumed stolen and stays rejected until re-login.
    if seller.token_invalid_before is not None:
        issued_at = token_issued_at(credentials.credentials)
        if issued_at is not None and issued_at < seller.token_invalid_before:
            raise unauthorized

    # Admin enforcement — see suspended_error for why this is a 403.
    if seller.suspended_at is not None:
        raise suspended_error()

    return seller


def get_current_admin(seller: Seller = Depends(get_current_seller)) -> Seller:
    """Gate for admin-only endpoints. 403 (not 404) so admins can't be
    discovered by probing — but a seller trying admin routes learns only
    that they lack permission."""
    if seller.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return seller
