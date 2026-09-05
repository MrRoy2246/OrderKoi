"""Authentication endpoints: signup, login, current user, password reset."""

import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_seller
from app.email import send_email
from app.models import PasswordResetToken, Seller, SubscriptionEvent, UpgradeRequest, utcnow
from app.schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SellerCreate,
    SellerLogin,
    SellerOut,
    SellerUpdate,
    SubscriptionEventOut,
    Token,
    UpgradeRequestCreate,
    UpgradeRequestOut,
)
from app.security import create_access_token, hash_password, verify_password
from app.slugs import unique_store_slug

router = APIRouter(prefix="/auth", tags=["auth"])

bearer_scheme = HTTPBearer(auto_error=False)

settings = get_settings()


@router.post(
    "/signup",
    response_model=SellerOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new seller account",
)
def signup(payload: SellerCreate, db: Session = Depends(get_db)) -> Seller:
    existing = db.query(Seller).filter(Seller.email == payload.email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Public order-form link, e.g. /order/abin-fashion — computed
    # before the insert because the column is NOT NULL
    store_slug = unique_store_slug(db, payload.store_name)

    seller = Seller(
        email=payload.email,
        store_name=payload.store_name,
        store_slug=store_slug,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
    )
    db.add(seller)
    try:
        db.commit()
    except IntegrityError:
        # Race condition: another signup used the same email meanwhile
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    db.refresh(seller)
    return seller


@router.post(
    "/login",
    response_model=Token,
    summary="Log in and receive an access token",
)
def login(payload: SellerLogin, db: Session = Depends(get_db)) -> Token:
    seller = db.query(Seller).filter(Seller.email == payload.email).first()

    # Same error for unknown email and wrong password — never reveal
    # which one was incorrect (prevents account enumeration)
    if seller is None or not verify_password(payload.password, seller.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    return Token(access_token=create_access_token(seller.id))


@router.get(
    "/me",
    response_model=SellerOut,
    summary="Get the currently logged-in seller",
)
def me(seller: Seller = Depends(get_current_seller)) -> Seller:
    return seller


@router.patch(
    "/me",
    response_model=SellerOut,
    summary="Update store profile (name, phone)",
)
def update_me(
    payload: SellerUpdate,
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> Seller:
    seller.store_name = payload.store_name.strip()
    seller.phone = payload.phone.strip() if payload.phone else None
    db.commit()
    db.refresh(seller)
    return seller


@router.post(
    "/forgot-password",
    summary="Request a password reset email",
)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict:
    """Always returns the same response — never reveal whether the
    email belongs to an account (prevents account enumeration)."""
    seller = db.query(Seller).filter(Seller.email == payload.email).first()

    if seller is not None:
        token = secrets.token_urlsafe(32)
        expires_at = utcnow() + timedelta(minutes=settings.reset_token_expire_minutes)

        db.add(
            PasswordResetToken(
                seller_id=seller.id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=expires_at,
            )
        )
        db.commit()

        reset_link = f"{settings.frontend_url}/reset-password?token={token}"
        send_email(
            to=seller.email,
            subject="Reset your OrderKoi password",
            body=(
                "Hello!\n\n"
                "We received a request to reset your OrderKoi password.\n\n"
                f"Open this link to choose a new password (valid for "
                f"{settings.reset_token_expire_minutes} minutes):\n\n"
                f"{reset_link}\n\n"
                "If you didn't request this, you can safely ignore this email — "
                "your password stays unchanged.\n\n"
                "— OrderKoi"
            ),
        )

    return {
        "detail": "If an account exists with this email, a password reset link has been sent."
    }


@router.post(
    "/reset-password",
    summary="Set a new password using a reset token",
)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    from datetime import timezone

    def as_aware(value):
        """SQLite returns naive datetimes — normalize before comparing."""
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    record = (
        db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    )

    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This reset link is invalid or has expired. Please request a new one.",
    )

    if (
        record is None
        or record.used_at is not None
        or as_aware(record.expires_at) < utcnow()
    ):
        raise invalid

    seller = db.get(Seller, record.seller_id)
    if seller is None:
        raise invalid

    seller.hashed_password = hash_password(payload.new_password)
    record.used_at = utcnow()
    db.commit()

    return {"detail": "Password updated. You can now log in with your new password."}


@router.post(
    "/upgrade-requests",
    response_model=UpgradeRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Request a Pro upgrade (admin verifies the payment)",
)
def create_upgrade_request(
    payload: UpgradeRequestCreate,
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> UpgradeRequest:
    if seller.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts don't need a subscription.",
        )

    pending = (
        db.query(UpgradeRequest)
        .filter(UpgradeRequest.seller_id == seller.id, UpgradeRequest.status == "pending")
        .first()
    )
    if pending is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending upgrade request — we'll review it shortly.",
        )

    request = UpgradeRequest(
        seller_id=seller.id,
        months=payload.months,
        payment_reference=payload.payment_reference,
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    # Tell every platform admin there's money waiting to be verified
    admins = db.query(Seller).filter(Seller.role == "admin").all()
    reference = payload.payment_reference or "not provided"
    for admin in admins:
        send_email(
            to=admin.email,
            subject=f"Pro upgrade request: {seller.store_name} ({payload.months} month{'s' if payload.months > 1 else ''})",
            body=(
                "A seller wants to upgrade to Pro.\n\n"
                f"Store: {seller.store_name} ({seller.email})\n"
                f"Duration: {payload.months} month{'s' if payload.months > 1 else ''}\n"
                f"Payment reference: {reference}\n\n"
                "Verify the payment, then approve or reject the request:\n"
                f"{settings.frontend_url}/admin/requests\n\n"
                "— OrderKoi"
            ),
        )

    return request


@router.get(
    "/upgrade-requests",
    response_model=list[UpgradeRequestOut],
    summary="My upgrade request history",
)
def my_upgrade_requests(
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> list[UpgradeRequest]:
    return (
        db.query(UpgradeRequest)
        .filter(UpgradeRequest.seller_id == seller.id)
        .order_by(UpgradeRequest.created_at.desc())
        .all()
    )


@router.get(
    "/subscription-history",
    response_model=list[SubscriptionEventOut],
    summary="My subscription history (activations, renewals, cancellations)",
)
def my_subscription_history(
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> list[SubscriptionEvent]:
    """The seller-side view of the ledger: every Pro activation,
    renewal and cancellation on this account, newest first. The admin
    sees the same events platform-wide; sellers see only their own."""
    return (
        db.query(SubscriptionEvent)
        .filter(SubscriptionEvent.seller_id == seller.id)
        .order_by(SubscriptionEvent.created_at.desc(), SubscriptionEvent.id.desc())
        .all()
    )


@router.post(
    "/cancel-subscription",
    response_model=SellerOut,
    summary="Cancel Pro immediately and return to the Free plan",
)
def cancel_subscription(
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> Seller:
    """Seller-initiated cancellation: Pro ends right away (no refund —
    manual bKash/Nagad payments are handled case by case) and the
    account drops back to the Free plan's one-time order allowance."""
    if seller.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts don't have a subscription.",
        )
    if seller.plan != "pro":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You're not on the Pro plan — nothing to cancel.",
        )

    seller.plan = "free"
    seller.plan_expires_at = None

    # Ledger: the admin sees exactly who cancelled and when — and the
    # seller's own Settings history shows it too (via /subscription-history)
    db.add(
        SubscriptionEvent(
            seller_id=seller.id,
            event="cancelled",
            months=None,
            note="cancelled by seller",
        )
    )
    db.commit()
    db.refresh(seller)

    # Business signal the platform owner wants to know about
    for admin in db.query(Seller).filter(Seller.role == "admin").all():
        send_email(
            to=admin.email,
            subject=f"Pro cancelled: {seller.store_name}",
            body=(
                "A seller cancelled their Pro subscription.\n\n"
                f"Store: {seller.store_name} ({seller.email})\n"
                "The account is back on the Free plan.\n\n"
                "Might be worth a friendly check-in to see what went wrong.\n\n"
                "— OrderKoi"
            ),
        )

    return seller


@router.get(
    "/token-check",
    include_in_schema=False,
)
def token_check(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Tiny helper so Swagger's Authorize button can be verified quickly."""
    if credentials is None:
        return {"authenticated": False}
    return {"authenticated": True, "scheme": credentials.scheme}
