"""Pydantic schemas — the shape of every request and response.

These are the API's public contract: they validate input coming in
and control exactly which fields are exposed going out.
"""

import enum
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth ----------

class SellerCreate(BaseModel):
    email: EmailStr
    # bcrypt operates on max 72 bytes; 64 chars is a sane upper bound
    password: str = Field(min_length=8, max_length=64)
    store_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, min_length=6, max_length=20)


class SellerLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=64)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=128)
    new_password: str = Field(min_length=8, max_length=64)


class SellerOut(BaseModel):
    """Public representation of a seller (no secrets)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    store_name: str
    store_slug: str
    phone: str | None
    role: Literal["seller", "admin"] = "seller"
    plan: Literal["free", "pro"] = "free"
    plan_expires_at: datetime | None = None
    email_verified: bool = False
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ResendVerificationRequest(BaseModel):
    """Ask for the signup verification email to be sent again."""
    email: EmailStr


class SellerUpdate(BaseModel):
    """Editable account fields (email and password stay as-is for now)."""
    store_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, min_length=6, max_length=20)


# ---------- Admin ----------

class AdminSellerOut(SellerOut):
    """Seller record as seen by the platform admin — with usage stats."""
    orders_count: int
    revenue: float  # non-cancelled orders only


class RecentSignupOut(BaseModel):
    """A store in the platform's "newest sellers" list on the overview."""

    store_name: str
    plan: Literal["free", "pro"]
    created_at: datetime


class MonthCount(BaseModel):
    """One month bucket in the admin's chart series (YYYY-MM)."""

    month: str
    count: int


class MonthValue(BaseModel):
    """One month bucket with a money value attached (YYYY-MM)."""

    month: str
    count: int
    value: float


class ChartBucket(BaseModel):
    """One chart bucket that follows the dashboard's date filter.

    The key is a day (YYYY-MM-DD) when the selected window is short
    (<= 90 days — daily granularity, like the orders chart) or a month
    (YYYY-MM) when the window is wider (year presets, long customs).
    The month-keyed fields mirror MonthValue/MonthCount so existing
    consumers keep working; the day-keyed fields mirror DailyValue.
    """

    # Day-keyed (short windows)
    date: str | None = None  # YYYY-MM-DD
    # Month-keyed (wide windows) — also present on day buckets for
    # backward compatibility with the old response contract
    month: str | None = None  # YYYY-MM
    count: int
    value: float = 0.0


class AdminStatsOut(BaseModel):
    """Platform-wide overview for the admin."""
    total_sellers: int
    pro_sellers: int
    free_sellers: int
    sellers_with_orders: int
    total_orders: int
    platform_revenue: float
    pending_upgrade_requests: int
    recent_signups: list[RecentSignupOut]
    # Subscription money — Pro activations the sellers actually paid
    # for (comp grants are excluded), computed from the ledger
    subscription_revenue_total: float = 0.0
    # Chart series (business-timezone buckets, oldest first) — all
    # three follow the date filter; granularity adapts to the window
    orders_daily: list["DailyCount"] = []  # the window, one bucket per day
    revenue_monthly: list[ChartBucket] = []  # sellers' GMV (daily for short windows)
    sellers_monthly: list[ChartBucket] = []  # signups (daily for short windows)
    subscription_monthly: list[ChartBucket] = []  # paid Pro money (daily for short windows)


class PlanUpdate(BaseModel):
    plan: Literal["free", "pro"]
    plan_expires_at: datetime | None = None
    # Manual Pro activation: how many months to grant. When given, the
    # server computes the expiry itself (new Pro = today + months,
    # active Pro extends from its current expiry) — same stacking rule
    # as approved upgrade requests, so paid time is never lost.
    months: Literal[1, 6, 12] | None = None
    # Comp grant: this Pro time is free (e.g. a gift month, a support
    # case). Comp activations are marked in the ledger and excluded
    # from subscription revenue totals.
    comp: bool = False


# Pro prices — served to the frontend at GET /pricing and used to
# compute subscription revenue from the ledger's months. The values
# come from .env (PRO_PRICE_1M/6M/12M) with the current defaults below,
# so a price change is an .env edit + restart: no code, no frontend
# rebuild. Admins must set all three together (the durations are the
# plan structure; a missing value falls back to the default).
class PricingOut(BaseModel):
    """Public pricing — one entry per Pro duration."""

    months: Literal[1, 6, 12]
    price: int


from app.config import get_settings  # noqa: E402 — after the class, for clarity


def pro_prices() -> dict[int, int]:
    """{months: price} from the current settings (env-overridable)."""
    settings = get_settings()
    return {
        1: settings.pro_price_1m,
        6: settings.pro_price_6m,
        12: settings.pro_price_12m,
    }


# ---------- Upgrade requests ----------

class UpgradeRequestCreate(BaseModel):
    """A seller asking to go Pro for a paid-for duration."""

    months: Literal[1, 6, 12]
    # bKash transaction ID so the admin can verify the payment
    payment_reference: str | None = Field(default=None, max_length=100)


class UpgradeRequestOut(BaseModel):
    """An upgrade request as the requesting seller sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    months: int
    status: Literal["pending", "approved", "rejected"]
    payment_reference: str | None
    created_at: datetime
    handled_at: datetime | None


class AdminUpgradeRequestOut(UpgradeRequestOut):
    """An upgrade request as the platform admin sees it."""

    seller_id: int
    seller_email: EmailStr
    store_name: str
    plan: Literal["free", "pro"]
    # The seller's *current* expiry — changes with every later renewal
    plan_expires_at: datetime | None
    # The expiry this request's approval produced (its own outcome,
    # frozen at handle time; null while pending or if rejected)
    granted_until: datetime | None


class UpgradeRequestAction(BaseModel):
    action: Literal["approve", "reject"]


class SubscriptionEventOut(BaseModel):
    """One subscription ledger entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int
    event: Literal["subscribed", "renewed", "cancelled"]
    months: int | None
    comp: bool = False
    # The upgrade request that caused this event, when there was one —
    # lets the seller's history dedupe request + activation into one row
    request_id: int | None = None
    note: str | None
    created_at: datetime


class AdminSubscriptionEventOut(SubscriptionEventOut):
    """A ledger entry as the admin sees it — with the store attached."""

    store_name: str
    seller_email: EmailStr


# ---------- Orders ----------

OrderStatusLiteral = Literal["placed", "confirmed", "shipped", "delivered", "cancelled"]


class OrderItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=999)
    price: float = Field(ge=0, description="Unit price")


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=6, max_length=20)
    customer_email: EmailStr | None = None
    customer_address: str | None = Field(default=None, max_length=500)
    items: list[OrderItem] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)


class OrderUpdate(BaseModel):
    """Editable fields — status changes go through their own endpoint."""
    customer_name: str | None = Field(default=None, min_length=1, max_length=100)
    customer_phone: str | None = Field(default=None, min_length=6, max_length=20)
    customer_email: EmailStr | None = None
    customer_address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)
    items: list[OrderItem] | None = Field(default=None, min_length=1, max_length=100)


class OrderStatusUpdate(BaseModel):
    status: OrderStatusLiteral


class StatusEvent(BaseModel):
    status: OrderStatusLiteral
    changed_at: datetime


class OrderOut(BaseModel):
    """Full order — returned only to the owning seller."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: int
    tracking_code: str
    customer_name: str
    customer_phone: str
    customer_email: str | None
    customer_address: str | None
    items: list[OrderItem]
    total_price: float
    notes: str | None
    status: OrderStatusLiteral
    source: Literal["dashboard", "form"] = "dashboard"
    status_history: list[StatusEvent]
    created_at: datetime
    updated_at: datetime


class OrderListOut(BaseModel):
    orders: list[OrderOut]
    total: int
    limit: int
    offset: int


# ---------- Public tracking ----------

class TrackingOut(BaseModel):
    """What a customer sees on the public tracking page.

    Deliberately excludes seller_id, customer_address and
    customer_phone — a tracking code should never leak them.
    """
    store_name: str
    order_number: int
    customer_name: str
    status: OrderStatusLiteral
    status_history: list[StatusEvent]
    created_at: datetime
    updated_at: datetime


# ---------- Public order form ----------

class PublicStoreOut(BaseModel):
    """The store header shown on the public order form (nothing else)."""

    store_name: str
    slug: str
    # False when a free-plan store has used its order allowance — the
    # form shows a "store paused" card instead of rejecting a filled-in
    # submission after the fact
    is_accepting_orders: bool = True


class PublicOrderCreate(BaseModel):
    """A customer's order submission from the public form.

    Items/prices are what the customer copied from the seller's
    Facebook post — the seller reviews and can edit them before
    confirming the order.
    """

    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=6, max_length=20)
    # Required on the public form — this is the address future
    # status-change notifications will be sent to
    customer_email: EmailStr
    customer_address: str = Field(min_length=1, max_length=500)
    items: list[OrderItem] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    # Honeypot — the real form renders this field invisible; humans
    # never fill it in. A non-empty value means a bot, and the request
    # gets a fake success instead of an order.
    website: str | None = Field(default=None, max_length=200)


class PublicOrderCreated(BaseModel):
    """Confirmation shown to the customer right after submitting."""

    order_number: int
    tracking_code: str
    store_name: str


# ---------- Analytics ----------

class DailyCount(BaseModel):
    date: str  # YYYY-MM-DD
    count: int


class DailyValue(BaseModel):
    """One day bucket with a money value attached (YYYY-MM-DD)."""

    date: str
    count: int
    value: float


class StatsSummary(BaseModel):
    """Dashboard overview for the logged-in seller."""
    range: Literal["today", "7d", "30d", "all", "custom"]
    total_orders: int  # orders within the selected range
    today_orders: int
    pending_orders: int  # placed + confirmed within the selected range
    delivered_orders: int
    cancelled_orders: int
    revenue: float  # non-cancelled orders within the range
    status_counts: dict[str, int]  # within the range
    daily: list[DailyValue]  # one bar per day of the range (max 1 year)
    month_orders: int  # lifetime non-cancelled orders (free-plan usage meter)
    plan_limit: int | None  # one-time allowance when on Free; None when on Pro
