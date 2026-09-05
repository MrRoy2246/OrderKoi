"""Orders endpoints — CRUD plus the status workflow.

Every route is scoped to the logged-in seller: a seller can only
see and touch their own orders, enforced in code (not just UI).
"""

import csv
import io
import random
import secrets
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_seller
from app.models import Order, OrderStatus, Seller, VALID_TRANSITIONS, pro_plan_active, utcnow
from app.schemas import (
    DailyValue,
    OrderCreate,
    OrderListOut,
    OrderOut,
    OrderStatusUpdate,
    OrderUpdate,
    StatsSummary,
)
from app.timezone import (
    business_today,
    day_bounds_utc,
    sqlite_shift_modifiers,
    to_business_time,
)

router = APIRouter(prefix="/orders", tags=["orders"])

settings = get_settings()


def _generate_tracking_code() -> str:
    """8 unguessable uppercase hex chars, e.g. 'A3F91C2B'."""
    return secrets.token_hex(4).upper()


# How many times to rebuild+retry when an insert hits a unique constraint
MAX_INSERT_ATTEMPTS = 5


def _insert_order_with_retry(db: Session, build) -> Order:
    """Insert an order, retrying when a unique constraint races us.

    Two things can collide under concurrent creation: the per-seller
    order number (two requests read the same max) and — very rarely —
    a random tracking code. Both surface as IntegrityError; both are
    resolved by rebuilding the order with a fresh number/code.

    `build` must construct and return a NEW Order each call.
    """
    for attempt in range(MAX_INSERT_ATTEMPTS):
        order = build()
        db.add(order)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if attempt == MAX_INSERT_ATTEMPTS - 1:
                # Astronomically unlikely (lost the race 5 times in a row)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Couldn't create the order — please try again.",
                )
            # Stagger retries with growing jitter so a pack of losers
            # doesn't re-read the same max and re-collide as a group
            time.sleep(random.uniform(0.02, 0.06) * (attempt + 1))
            continue
        db.refresh(order)
        return order


def _compute_total(items: list[dict]) -> float:
    return round(sum(item["quantity"] * item["price"] for item in items), 2)


def _initial_history() -> list[dict]:
    return [{"status": OrderStatus.PLACED.value, "changed_at": utcnow().isoformat()}]


def _get_owned_order(order_id: int, seller: Seller, db: Session) -> Order:
    """Fetch an order that belongs to the seller — 404 otherwise.

    404 (not 403) so outsiders can't even confirm an order id exists.
    """
    order = db.get(Order, order_id)
    if order is None or order.seller_id != seller.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return order


def _lifetime_order_count(seller: Seller, db: Session) -> int:
    """Non-cancelled orders this seller has EVER received — the free
    plan's allowance is one-time, not monthly.

    Cancelled orders don't count: a seller who cancels a mistake or
    form spam gets that allowance unit back.
    """
    return (
        db.query(func.count(Order.id))
        .filter(
            Order.seller_id == seller.id,
            Order.status != OrderStatus.CANCELLED.value,
        )
        .scalar()
    )


def _check_plan_limit(seller: Seller, db: Session) -> None:
    """Free plan: a one-time order allowance (15 orders, ever). Once
    it's used up the seller needs Pro to keep receiving orders. Pro is
    unlimited; admins don't place orders at all (their accounts are
    platform accounts, not shops)."""
    if seller.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts are platform accounts — they don't place orders. "
            "Log in with a seller account to manage orders.",
        )
    if pro_plan_active(seller):
        return

    used = _lifetime_order_count(seller, db)
    if used >= settings.free_plan_orders:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"You've used all {settings.free_plan_orders} free orders. "
                "Upgrade to Pro for unlimited orders — "
                "your existing orders and data stay exactly as they are."
            ),
        )


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new order",
)
def create_order(
    payload: OrderCreate,
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> Order:
    _check_plan_limit(seller, db)

    def build() -> Order:
        # Per-seller sequence: highest existing number + 1, read fresh
        # on every attempt so a racing insert is picked up on retry
        max_number = (
            db.query(func.max(Order.order_number))
            .filter(Order.seller_id == seller.id)
            .scalar()
        )
        return Order(
            seller_id=seller.id,
            order_number=(max_number or 0) + 1,
            tracking_code=_generate_tracking_code(),
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            customer_email=payload.customer_email,
            customer_address=payload.customer_address,
            items=[item.model_dump() for item in payload.items],
            total_price=_compute_total([item.model_dump() for item in payload.items]),
            notes=payload.notes,
            status=OrderStatus.PLACED.value,
            source="dashboard",
            status_history=_initial_history(),
        )

    return _insert_order_with_retry(db, build)


def _apply_order_filters(query, status_filter, q, start=None, end=None):
    """Shared filtering for the list and CSV-export endpoints — the
    export must show exactly what the list shows.

    start/end are business-timezone calendar dates (YYYY-MM-DD) and
    are inclusive: an order created any time during the end date
    still matches.
    """
    if status_filter:
        # Multiple values allowed, e.g. ?status=placed&status=confirmed
        query = query.filter(Order.status.in_([s.value for s in status_filter]))

    if start is not None:
        query = query.filter(Order.created_at >= day_bounds_utc(start)[0])
    if end is not None:
        # < start-of-the-day-after, so the end date's whole day is included
        query = query.filter(Order.created_at < day_bounds_utc(end)[1])

    if q:
        term = q.strip()
        pattern = f"%{term}%"
        conditions = [
            Order.customer_name.ilike(pattern),
            Order.customer_phone.ilike(pattern),
            Order.customer_email.ilike(pattern),
        ]
        if term.isdigit():
            conditions.append(Order.order_number == int(term))
        query = query.filter(or_(*conditions))

    return query


def _validate_date_range(start: date | None, end: date | None) -> None:
    """Shared guard for the list and export endpoints — same rules,
    same error, so the UI can treat both identically."""
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Start date must be before (or equal to) the end date.",
        )


@router.get(
    "",
    response_model=OrderListOut,
    summary="List my orders (filter by status, search, paginate)",
)
def list_orders(
    status_filter: list[OrderStatus] | None = Query(
        default=None, alias="status", description="Filter by one or more statuses"
    ),
    q: str | None = Query(default=None, max_length=100, description="Search name/phone/email/order number"),
    start: date | None = Query(default=None, description="Range start (YYYY-MM-DD, inclusive)"),
    end: date | None = Query(default=None, description="Range end (YYYY-MM-DD, inclusive)"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> dict:
    _validate_date_range(start, end)
    query = _apply_order_filters(
        db.query(Order).filter(Order.seller_id == seller.id), status_filter, q, start, end
    )

    total = query.count()
    orders = (
        query.order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"orders": orders, "total": total, "limit": limit, "offset": offset}


# Safety valve: a full export is bounded so it can't be used to drag
# unbounded rows through memory (10k rows ≈ a few MB of CSV)
EXPORT_MAX_ROWS = 10_000


# NOTE: registered before /{order_id} so "export" isn't captured as an id
@router.get(
    "/export",
    summary="Export my orders as CSV (honors the same filters as the list)",
)
def export_orders_csv(
    status_filter: list[OrderStatus] | None = Query(
        default=None, alias="status", description="Filter by one or more statuses"
    ),
    q: str | None = Query(default=None, max_length=100, description="Search name/phone/email/order number"),
    start: date | None = Query(default=None, description="Range start (YYYY-MM-DD, inclusive)"),
    end: date | None = Query(default=None, description="Range end (YYYY-MM-DD, inclusive)"),
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    _validate_date_range(start, end)
    query = _apply_order_filters(
        db.query(Order).filter(Order.seller_id == seller.id), status_filter, q, start, end
    )
    orders = (
        query.order_by(Order.created_at.desc(), Order.id.desc())
        .limit(EXPORT_MAX_ROWS)
        .all()
    )

    buffer = io.StringIO()
    # UTF-8 BOM so Excel detects the encoding (names can be Bengali)
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Order #",
            "Date",
            "Customer name",
            "Phone",
            "Email",
            "Address",
            "Items",
            "Total (Tk)",
            "Status",
            "Source",
            "Tracking code",
            "Notes",
        ]
    )
    for order in orders:
        writer.writerow(
            [
                order.order_number,
                to_business_time(order.created_at).strftime("%Y-%m-%d %H:%M"),
                order.customer_name,
                order.customer_phone,
                order.customer_email or "",
                order.customer_address or "",
                "; ".join(f"{item['name']} x{item['quantity']}" for item in order.items),
                f"{order.total_price:.2f}",
                order.status,
                order.source,
                order.tracking_code,
                order.notes or "",
            ]
        )

    filename = f"orderkoi-orders-{business_today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# NOTE: registered before /{order_id} so "stats" isn't captured as an id
@router.get(
    "/stats/summary",
    response_model=StatsSummary,
    summary="Dashboard statistics for the logged-in seller",
)
def stats_summary(
    range_filter: str = Query(
        default="all",
        alias="range",
        pattern="^(today|7d|30d|all|custom)$",
        description="today | 7d | 30d | all | custom (needs start & end)",
    ),
    start: date | None = Query(default=None, description="Custom range start (YYYY-MM-DD)"),
    end: date | None = Query(default=None, description="Custom range end (YYYY-MM-DD)"),
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> dict:
    today = business_today()
    if range_filter == "custom":
        if start is None or end is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Custom range needs both start and end dates.",
            )
        if start > end:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Start date must be before (or equal to) the end date.",
            )
        window_days = (end - start).days + 1
        if window_days > 366:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Custom range can span at most one year.",
            )
        window_start, window_end = start, end
    elif range_filter == "today":
        window_days, window_start, window_end = 1, today, today
    elif range_filter == "7d":
        window_days, window_start, window_end = 7, today - timedelta(days=6), today
    elif range_filter == "30d":
        window_days, window_start, window_end = 30, today - timedelta(days=29), today
    else:  # all — cap the chart at the most recent 30 days
        window_days, window_start, window_end = 30, today - timedelta(days=29), today

    # Day boundaries in the business timezone, converted to naive UTC —
    # exactly how created_at is stored, so comparisons are exact.
    window_start_dt, _ = day_bounds_utc(window_start)
    _, window_end_dt = day_bounds_utc(window_end)  # include the end date's full day
    today_start_dt, tomorrow_start_dt = day_bounds_utc(today)

    owned = Order.seller_id == seller.id
    in_window = (Order.created_at >= window_start_dt) & (Order.created_at < window_end_dt)

    # Windowed status counts + revenue in one grouped query — the DB
    # does the aggregation, so a seller with 100k orders costs the same
    # as one with 10 (no more loading history into Python).
    windowed_rows = (
        db.query(
            Order.status,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_price), 0.0),
        )
        .filter(owned, in_window)
        .group_by(Order.status)
        .all()
    )

    status_counts = {status.value: 0 for status in OrderStatus}
    total_in_range = 0
    revenue = 0.0
    for order_status, count, status_total in windowed_rows:
        status_counts[order_status] = status_counts.get(order_status, 0) + count
        total_in_range += count
        if order_status != OrderStatus.CANCELLED.value:
            revenue += float(status_total)

    today_orders = (
        db.query(func.count(Order.id))
        .filter(
            owned,
            Order.created_at >= today_start_dt,
            Order.created_at < tomorrow_start_dt,
        )
        .scalar()
    )

    # Pending within the selected window — the dashboard card shows this
    # number and links to the orders list filtered to the same window,
    # so the two must always agree
    pending_in_window = (
        status_counts[OrderStatus.PLACED.value]
        + status_counts[OrderStatus.CONFIRMED.value]
    )

    # Group by the *business-local* date: an order at 20:00 UTC is
    # 02:00 next day in Dhaka and belongs on that day's bar. SQLite
    # date() modifiers do the shift in SQL (no per-row Python).
    # Revenue rides along so the same series powers a money chart —
    # cancelled orders count toward nothing (no bar, no money).
    day_expr = func.date(Order.created_at, *sqlite_shift_modifiers())
    daily_rows = (
        db.query(
            day_expr,
            func.count(Order.id),
            func.coalesce(
                func.sum(
                    case((Order.status != OrderStatus.CANCELLED.value, Order.total_price))
                ),
                0.0,
            ),
        )
        .filter(owned, in_window)
        .group_by(day_expr)
        .all()
    )
    daily_map = {str(day): (int(count), round(float(total), 2)) for day, count, total in daily_rows}

    # Fill the full window so the chart shows quiet days too
    daily = [
        DailyValue(
            date=(window_start + timedelta(days=i)).isoformat(),
            count=daily_map.get((window_start + timedelta(days=i)).isoformat(), (0, 0.0))[0],
            value=daily_map.get((window_start + timedelta(days=i)).isoformat(), (0, 0.0))[1],
        )
        for i in range(window_days)
    ]

    return {
        "range": range_filter,
        "total_orders": total_in_range,
        "today_orders": today_orders,
        "pending_orders": pending_in_window,
        "delivered_orders": status_counts[OrderStatus.DELIVERED.value],
        "cancelled_orders": status_counts[OrderStatus.CANCELLED.value],
        "revenue": round(revenue, 2),
        "status_counts": status_counts,
        "daily": daily,
        # The free plan meter: non-cancelled orders this account has
        # ever placed (one-time allowance, not monthly)
        "month_orders": _lifetime_order_count(seller, db),
        # Free plan allowance (Pro sellers see null = unlimited)
        "plan_limit": None
        if pro_plan_active(seller) or seller.role == "admin"
        else settings.free_plan_orders,
    }


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="Get one of my orders",
)
def get_order(
    order_id: int,
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> Order:
    return _get_owned_order(order_id, seller, db)


@router.patch(
    "/{order_id}",
    response_model=OrderOut,
    summary="Edit order details (not status)",
)
def update_order(
    order_id: int,
    payload: OrderUpdate,
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> Order:
    order = _get_owned_order(order_id, seller, db)

    data = payload.model_dump(exclude_unset=True)

    # A delivered/cancelled order is history — lock it
    if order.status in (OrderStatus.DELIVERED.value, OrderStatus.CANCELLED.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot edit an order that is {order.status}.",
        )

    if "items" in data:
        order.items = data.pop("items")
        order.total_price = _compute_total(order.items)

    for field, value in data.items():
        setattr(order, field, value)

    db.commit()
    db.refresh(order)
    return order


@router.patch(
    "/{order_id}/status",
    response_model=OrderOut,
    summary="Advance the order status (workflow-enforced)",
)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> Order:
    order = _get_owned_order(order_id, seller, db)

    new_status = payload.status
    allowed = VALID_TRANSITIONS.get(order.status, set())

    if new_status == order.status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is already {new_status}.",
        )
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot move from '{order.status}' to '{new_status}'. "
            f"Valid next steps: {sorted(allowed) if allowed else 'none (final state)'}.",
        )

    order.status = new_status
    order.status_history = order.status_history + [
        {"status": new_status, "changed_at": utcnow().isoformat()}
    ]

    db.commit()
    db.refresh(order)
    return order


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an order (only while placed)",
)
def delete_order(
    order_id: int,
    seller: Seller = Depends(get_current_seller),
    db: Session = Depends(get_db),
) -> None:
    order = _get_owned_order(order_id, seller, db)

    # Only allow deleting mistakes before any real progress happens
    if order.status != OrderStatus.PLACED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only orders still in 'placed' status can be deleted.",
        )

    db.delete(order)
    db.commit()
