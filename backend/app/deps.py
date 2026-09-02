"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Seller
from app.security import decode_access_token

# Swagger shows a 🔒 Authorize button; the frontend sends
# "Authorization: Bearer <token>"
bearer_scheme = HTTPBearer(auto_error=False)


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
