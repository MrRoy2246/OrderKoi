"""SQLAlchemy ORM models — the database schema."""

import enum

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    """Timezone-aware UTC now (naive datetimes cause subtle bugs)."""
    return datetime.now(timezone.utc)


def as_aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes — normalize before comparing."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def pro_plan_active(seller: "Seller") -> bool:
    """Is this seller's Pro subscription currently in force?

    A Pro plan with an expiry date in the past is treated as expired —
    the seller is effectively back on Free until they renew.
    """
    if seller.plan != "pro":
        return False
    if seller.plan_expires_at is None:
        return True  # no expiry set — lifetime/legacy Pro
    return as_aware(seller.plan_expires_at) >= utcnow()


class OrderStatus(str, enum.Enum):
    """Order lifecycle — the workflow sellers advance through."""

    PLACED = "placed"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# Which statuses each status may move to. Enforced by the API so
# orders can never skip steps (placed -> delivered) or revive
# after being cancelled/delivered.
VALID_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PLACED.value: {OrderStatus.CONFIRMED.value, OrderStatus.CANCELLED.value},
    OrderStatus.CONFIRMED.value: {OrderStatus.SHIPPED.value, OrderStatus.CANCELLED.value},
    OrderStatus.SHIPPED.value: {OrderStatus.DELIVERED.value, OrderStatus.CANCELLED.value},
    OrderStatus.DELIVERED.value: set(),
    OrderStatus.CANCELLED.value: set(),
}


class Seller(Base):
    """A seller account — one shop owner.

    role: "seller" (normal) or "admin" (platform owner — that's you).
    plan: "free" (monthly order cap) or "pro" (subscribed, unlimited).
    """

    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Store name shown to customers on the public tracking page
    store_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Public URL part for the customer order form: /order/{store_slug}
    store_slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Never store plain passwords — bcrypt hash only
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(String(20), default="seller", nullable=False)
    plan: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Seller id={self.id} email={self.email!r} store={self.store_name!r}>"


class PasswordResetToken(Base):
    """A single-use password reset token for a seller.

    Only the SHA-256 hash of the token is stored — a database leak
    must never be enough to reset anyone's password.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("sellers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UpgradeRequest(Base):
    """A seller's request to upgrade to Pro for N months.

    Real-world flow (manual payments, Bangladesh-style): the seller pays
    via bKash/Nagad, submits the request with the transaction reference,
    and the platform admin verifies the payment and approves — which
    activates Pro until the paid-for date. Rejected requests stay as
    a record for both sides.
    """

    __tablename__ = "upgrade_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("sellers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Paid-for duration: 1, 6 or 12 months
    months: Mapped[int] = mapped_column(Integer, nullable=False)
    # bKash/Nagad transaction ID the admin verifies against
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # pending -> approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Snapshot of the expiry this approval produced (after stacking on
    # any remaining time) — the seller's *current* expiry changes with
    # every later renewal, but this row keeps its own outcome forever
    granted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<UpgradeRequest id={self.id} seller_id={self.seller_id} months={self.months} status={self.status!r}>"


class SubscriptionEvent(Base):
    """Audit trail of subscription changes — the admin's ledger.

    Every plan change leaves a row here: an approved upgrade request
    ("subscribed"/"renewed"), a seller-initiated cancellation, or a
    manual plan change by the admin. This is how the platform owner
    knows who subscribed when, and who cancelled when.
    """

    __tablename__ = "subscription_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("sellers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # subscribed | renewed | cancelled
    event: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # paid-for duration for subscribed/renewed; None for cancelled
    months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # human context, e.g. "active until 1 Mar 2027" or "cancelled by seller"
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SubscriptionEvent id={self.id} seller_id={self.seller_id} event={self.event!r}>"


class Order(Base):
    """A customer order placed with a seller."""

    __tablename__ = "orders"
    # Two requests can read the same "max order number" at the same
    # moment; the DB itself must refuse the resulting duplicate.
    __table_args__ = (
        UniqueConstraint("seller_id", "order_number", name="uq_orders_seller_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("sellers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Human-friendly per-seller sequence: seller's 1st, 2nd, 3rd order...
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Public code customers use to track — unguessable, unique
    tracking_code: Mapped[str] = mapped_column(String(12), unique=True, index=True, nullable=False)

    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Optional today — the hook for future customer notifications
    # (email on status change). Collected from both order forms.
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # [{name, quantity, price}] — JSON works on SQLite and PostgreSQL
    items: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Computed server-side from items — never trusted from the client
    total_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.PLACED.value, nullable=False, index=True)
    # [{status, changed_at}] — powers the customer-facing timeline
    status_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # How the order entered the system: "dashboard" (seller typed it)
    # or "form" (customer submitted it via the public order form)
    source: Mapped[str] = mapped_column(String(20), default="dashboard", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} order_number={self.order_number} "
            f"status={self.status!r} seller_id={self.seller_id}>"
        )
