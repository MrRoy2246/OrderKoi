"""Admin endpoints — the platform owner's view of the business.

Admin-only: see every seller, who subscribed (Pro) vs free,
platform-wide stats, manage subscription plans, and approve or reject
Pro upgrade requests (the seller pays via bKash first, then the
admin verifies the payment and activates the paid-for duration).
"""

import calendar
import csv
import io
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_admin
from app.email import send_email
from app.models import (
    Order,
    OrderStatus,
    Seller,
    SubscriptionEvent,
    UpgradeRequest,
    pro_plan_active,
    utcnow,
)
from app.schemas import (
    AdminSellerListOut,
    AdminSellerOut,
    AdminStatsOut,
    AdminSubscriptionEventOut,
    AdminUpgradeRequestOut,
    ChartBucket,
    DailyCount,
    PlanUpdate,
    RecentSignupOut,
    UpgradeRequestAction,
    pro_prices,
)
from app.timezone import (
    business_day,
    business_month,
    business_now,
    business_today,
    business_tz,
    day_bounds_utc,
    to_business_time,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _add_months(moment: datetime, months: int) -> datetime:
    """Same time-of-day, N calendar months later (clamped to month length)."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _paid_event_filters() -> tuple:
    """WHERE conditions shared by every paid-ledger query: subscription
    or renewal entries, not comped, with a known duration."""
    return (
        SubscriptionEvent.event.in_(["subscribed", "renewed"]),
        SubscriptionEvent.comp.is_(False),
        SubscriptionEvent.months.isnot(None),
    )


def _price_expr(prices: dict[int, int]):
    """SQL: the current price of a ledger entry's duration. Entries with
    an unknown duration (data oddities) contribute nothing — same rule
    the Python-side summation always had."""
    return case(
        *[(SubscriptionEvent.months == months, price) for months, price in prices.items()],
        else_=0,
    )


def _subscription_revenue(db: Session, since: datetime | None = None) -> float:
    """Total money sellers paid for Pro — comp (free) grants excluded,
    valued at current prices (env-driven — GET /pricing shows the same
    numbers), summed entirely in SQL so the ledger can grow forever
    without this getting heavier. `since` (aware UTC) limits the sum to
    recent entries, e.g. a 30-day pulse."""
    query = db.query(
        func.coalesce(func.sum(_price_expr(pro_prices())), 0.0)
    ).filter(*_paid_event_filters())
    if since is not None:
        query = query.filter(SubscriptionEvent.created_at >= since)
    return float(query.scalar())


def _paid_subscription_series(
    db: Session, key_expr, window: tuple[datetime, datetime | None] | None = None
) -> dict[str, tuple[int, float]]:
    """Paid ledger entries grouped by a business-local day/month key
    expression, valued at current prices: {key: (count, money)}.

    Grouping and pricing both happen in SQL. `window` is an optional
    [start, end) pair of aware-UTC bounds on created_at (end may be
    None for "from start onward")."""
    query = db.query(
        key_expr,
        func.count(SubscriptionEvent.id),
        func.coalesce(func.sum(_price_expr(pro_prices())), 0.0),
    ).filter(*_paid_event_filters())
    if window is not None:
        start_dt, end_dt = window
        query = query.filter(SubscriptionEvent.created_at >= start_dt)
        if end_dt is not None:
            query = query.filter(SubscriptionEvent.created_at < end_dt)
    return {
        str(key): (int(count), round(float(value), 2))
        for key, count, value in query.group_by(key_expr).all()
    }


@router.get(
    "/sellers",
    response_model=AdminSellerListOut,
    summary="List sellers (paginated, filter by plan, searchable)",
)
def list_sellers(
    plan: str = Query(
        default="all",
        pattern="^(all|pro|free)$",
        description="all | pro (active) | free (incl. expired Pro)",
    ),
    q: str | None = Query(
        default=None, max_length=100, description="Search store name, email, or slug"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001 — guards access
) -> dict:
    """The seller directory, one page at a time.

    Everything the AdminSellers page can filter on is applied in SQL —
    plan tab, search, pagination — so the endpoint costs the same with
    50 sellers or 500,000. Admin accounts are platform accounts, not
    shops, so they never appear (the UI never showed them anyway).
    """
    # Active Pro, in SQL — same rule as pro_plan_active(): plan says
    # pro AND (no expiry set, or expiry still ahead)
    now = utcnow()
    active_pro = (Seller.plan == "pro") & (
        Seller.plan_expires_at.is_(None) | (Seller.plan_expires_at >= now)
    )

    query = db.query(Seller).filter(Seller.role != "admin")
    if plan == "pro":
        query = query.filter(active_pro)
    elif plan == "free":
        query = query.filter(~active_pro)

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.filter(
            Seller.store_name.ilike(pattern)
            | Seller.email.ilike(pattern)
            | Seller.store_slug.ilike(pattern)
        )

    total = query.count()
    sellers = (
        query.order_by(Seller.created_at.desc(), Seller.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Usage stats for just this page's sellers — never the whole
    # platform's order table in one aggregate
    page_ids = [seller.id for seller in sellers]
    order_stats: dict[int, tuple[int, float]] = {}
    if page_ids:
        order_stats = {
            seller_id: (int(count), float(revenue))
            for seller_id, count, revenue in db.query(
                Order.seller_id,
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_price), 0.0),
            )
            .filter(
                Order.seller_id.in_(page_ids),
                Order.status != OrderStatus.CANCELLED.value,
            )
            .group_by(Order.seller_id)
            .all()
        }

    return {
        "sellers": [
            {
                **{column.name: getattr(seller, column.name) for column in Seller.__table__.columns},
                "orders_count": order_stats.get(seller.id, (0, 0.0))[0],
                "revenue": round(order_stats.get(seller.id, (0, 0.0))[1], 2),
            }
            for seller in sellers
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/stats",
    response_model=AdminStatsOut,
    summary="Platform-wide statistics",
)
def platform_stats(
    days: int = 30,
    start: date | None = Query(default=None, description="Custom range start (YYYY-MM-DD, inclusive)"),
    end: date | None = Query(default=None, description="Custom range end (YYYY-MM-DD, inclusive)"),
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001
) -> dict:
    # The daily chart's window: either a rolling `days` count (7 / 30 /
    # 90, clamped) or an explicit custom range (start..end inclusive,
    # at most one year). Custom wins when both are given.
    today = business_today()
    if start is not None or end is not None:
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
        if (end - start).days + 1 > 366:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Custom range can span at most one year.",
            )
        window_start, window_end, window_days = start, end, (end - start).days + 1
    else:
        days = max(1, min(days, 90))
        window_start = today - timedelta(days=days - 1)
        window_end = today
        window_days = days
    # Aware-UTC window boundaries (timestamptz comparisons)
    window_start_dt, _ = day_bounds_utc(window_start)
    _, window_end_dt = day_bounds_utc(window_end)
    # Monthly series (GMV / signups / subscription money): scoped to
    # the window when the window spans 2+ months (This/Previous year,
    # custom ranges); short rolling presets keep the trailing
    # 12-month context — a 7-day window bucketed by month is one
    # lonely bar, and money views want the longer story.
    # Shop counts straight from SQL — never load the sellers table into
    # Python (500k sellers must cost the same as 50). Active Pro is the
    # same rule as pro_plan_active(), evaluated in the database.
    now = utcnow()
    active_pro = (Seller.plan == "pro") & (
        Seller.plan_expires_at.is_(None) | (Seller.plan_expires_at >= now)
    )
    shops = Seller.role == "seller"

    total_sellers = db.query(func.count(Seller.id)).filter(shops).scalar()
    pro_sellers = db.query(func.count(Seller.id)).filter(shops, active_pro).scalar()
    free_sellers = total_sellers - pro_sellers
    explicit_range = start is not None or end is not None

    # All-time platform totals in ONE aggregate query — count, revenue,
    # and distinct shops, in a single pass over non-cancelled orders
    # (no group-by, no ORM rows materialized).
    totals = db.query(
        func.count(Order.id),
        func.coalesce(func.sum(Order.total_price), 0.0),
        func.count(func.distinct(Order.seller_id)),
    ).filter(Order.status != OrderStatus.CANCELLED.value).one()
    total_orders = int(totals[0])
    platform_revenue = round(float(totals[1]), 2)
    sellers_with_orders = int(totals[2])

    pending_upgrades = (
        db.query(func.count(UpgradeRequest.id))
        .filter(UpgradeRequest.status == "pending")
        .scalar()
    )

    # The 5 newest stores — the platform's heartbeat on the overview
    recent = (
        db.query(Seller)
        .filter(Seller.role == "seller")
        .order_by(Seller.created_at.desc())
        .limit(5)
        .all()
    )
    recent_signups = [
        RecentSignupOut(
            store_name=s.store_name,
            plan="pro" if pro_plan_active(s) else "free",
            created_at=s.created_at,
        )
        for s in recent
    ]

    # Subscription money — what the sellers actually paid for Pro
    # (comp grants don't count). The all-time total anchors the
    # "Your earnings" KPI's context line; the chart series are built
    # per-branch below, grouped in SQL (_paid_subscription_series) so
    # the ledger never loads into Python.
    subscription_revenue_total = _subscription_revenue(db)

    # ---- Chart series (business-timezone buckets, oldest first) ----

    # Orders per day, over the window chosen above (7 / 30 / 90-day
    # presets or a custom range — the dashboard's range filter).
    day_expr = business_day(Order.created_at)
    daily_rows = (
        db.query(
            day_expr,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_price), 0.0),
        )
        .filter(
            Order.created_at >= window_start_dt,
            Order.created_at < window_end_dt,
            Order.status != OrderStatus.CANCELLED.value,
        )
        .group_by(day_expr)
        .all()
    )
    daily_map = {
        str(day): (int(count), round(float(total), 2)) for day, count, total in daily_rows
    }
    orders_daily = [
        DailyCount(
            date=(window_start + timedelta(days=i)).isoformat(),
            count=daily_map.get((window_start + timedelta(days=i)).isoformat(), (0, 0.0))[0],
        )
        for i in range(window_days)
    ]

    # Month buckets for GMV + signups: group by business-local YYYY-MM.
    # Keys come from plain (year, month) arithmetic on the *local* date —
    # UTC-space month arithmetic drifts by the tz offset (Dhaka +6) and
    # produces duplicate or skipped months.
    #
    # Granularity follows the SELECTED window (the dashboard's date
    # filter): daily buckets for short windows (<= 90 days — same
    # shape as the orders chart), monthly buckets for wider ones
    # (year presets, long customs — capped at 12 buckets). Every
    # chart therefore always follows the filter.
    now_local = business_now()
    now_month_index = now_local.year * 12 + (now_local.month - 1)
    use_daily = window_days <= 90
    if use_daily:
        # Day buckets: the daily orders query already carries each day's
        # GMV — reuse its rows instead of running the same query twice
        gmv_map = {
            str(day): (int(count), round(float(total), 2))
            for day, count, total in daily_rows
        }
        signup_day_expr = business_day(Seller.created_at)
        signup_day_rows = (
            db.query(signup_day_expr, func.count(Seller.id))
            .filter(
                Seller.role == "seller",
                Seller.created_at >= window_start_dt,
                Seller.created_at < window_end_dt,
            )
            .group_by(signup_day_expr)
            .all()
        )
        signup_map = {str(day): int(count) for day, count in signup_day_rows}
        # Paid-Pro money by day, from the ledger (grouped in SQL)
        sub_day_map = _paid_subscription_series(
            db,
            business_day(SubscriptionEvent.created_at),
            window=(window_start_dt, window_end_dt),
        )

        # Shared series of day keys — one pass builds all three series
        day_keys = [(window_start + timedelta(days=i)).isoformat() for i in range(window_days)]
        revenue_monthly = [
            ChartBucket(
                date=key,
                month=key,
                count=gmv_map.get(key, (0, 0.0))[0],
                value=gmv_map.get(key, (0, 0.0))[1],
            )
            for key in day_keys
        ]
        sellers_monthly = [
            ChartBucket(
                date=key,
                month=key,
                count=signup_map.get(key, 0),
                value=signup_map.get(key, 0),
            )
            for key in day_keys
        ]
        subscription_monthly = [
            ChartBucket(
                date=key,
                month=key,
                count=sub_day_map.get(key, (0, 0.0))[0],
                value=sub_day_map.get(key, (0, 0.0))[1],
            )
            for key in day_keys
        ]
    else:
        # Month buckets. Scope rule: the window's own months when it
        # spans 2+ calendar months; trailing 12 months otherwise (the
        # window is year-wide here, so this is just a safety clamp).
        if explicit_range:
            start_local = to_business_time(window_start_dt)
            s_idx = start_local.year * 12 + (start_local.month - 1)
            end_local = to_business_time(window_end_dt)
            e_idx = end_local.year * 12 + (end_local.month - 1)
            if e_idx > s_idx:  # 2+ calendar months → scope the series
                start_month_index, end_month_index = s_idx, e_idx
            else:  # single-month window → keep the 12-month context
                start_month_index, end_month_index = now_month_index - 11, now_month_index
        else:
            start_month_index, end_month_index = now_month_index - 11, now_month_index
        # Cap: at most 12 buckets ending on the series' end month (a
        # >1-year window still shows the most recent year)
        first_index = max(start_month_index, end_month_index - 11)
        back_year, back_month = divmod(first_index, 12)
        first_bucket_start = datetime(back_year, back_month + 1, 1, tzinfo=business_tz).astimezone(
            timezone.utc
        )
        month_expr = business_month(Order.created_at)
        gmv_rows = (
            db.query(
                month_expr,
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_price), 0.0),
            )
            .filter(
                Order.created_at >= first_bucket_start,
                Order.status != OrderStatus.CANCELLED.value,
            )
            .group_by(month_expr)
            .all()
        )
        gmv_map = {
            str(month): (int(count), round(float(total), 2))
            for month, count, total in gmv_rows
        }

        seller_month_expr = business_month(Seller.created_at)
        signup_rows = (
            db.query(seller_month_expr, func.count(Seller.id))
            .filter(
                Seller.role == "seller",
                Seller.created_at >= first_bucket_start,
            )
            .group_by(seller_month_expr)
            .all()
        )
        signup_map = {str(month): int(count) for month, count in signup_rows}

        # Paid-Pro money by month for the same span, grouped in SQL
        sub_month_map = _paid_subscription_series(
            db,
            business_month(SubscriptionEvent.created_at),
            window=(first_bucket_start, None),
        )

        # Build the month series covering the window (oldest first)
        months_series: list[ChartBucket] = []
        cursor = first_index
        while cursor <= end_month_index:
            year, month0 = divmod(cursor, 12)
            key = f"{year:04d}-{month0 + 1:02d}"
            count, value = gmv_map.get(key, (0, 0.0))
            months_series.append(
                ChartBucket(month=key, count=count, value=value)
            )
            cursor += 1
        revenue_monthly = months_series
        subscription_monthly = [
            ChartBucket(
                month=m.month,
                count=sub_month_map.get(m.month, (0, 0.0))[0],
                value=sub_month_map.get(m.month, (0, 0.0))[1],
            )
            for m in months_series
        ]
        sellers_monthly = [
            ChartBucket(month=m.month, count=signup_map.get(m.month, 0), value=signup_map.get(m.month, 0))
            for m in months_series
        ]

    return {
        "total_sellers": total_sellers,
        "pro_sellers": pro_sellers,
        "free_sellers": free_sellers,
        "sellers_with_orders": sellers_with_orders,
        "total_orders": total_orders,
        "platform_revenue": platform_revenue,
        "pending_upgrade_requests": pending_upgrades,
        "recent_signups": recent_signups,
        "subscription_revenue_total": round(subscription_revenue_total, 2),
        "orders_daily": orders_daily,
        "revenue_monthly": revenue_monthly,
        "sellers_monthly": sellers_monthly,
        "subscription_monthly": subscription_monthly,
    }


@router.get(
    "/sellers/{seller_id}/stats",
    summary="One shop's performance — daily orders and revenue over a window",
)
def seller_shop_stats(
    seller_id: int,
    start: date | None = Query(default=None, description="Window start (YYYY-MM-DD, inclusive)"),
    end: date | None = Query(default=None, description="Window end (YYYY-MM-DD, inclusive)"),
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001 — guards access
) -> dict:
    """Admin view of a single shop's numbers. Same window rules as the
    platform stats: defaults to the last 30 days, explicit start/end
    (inclusive, business timezone), at most one year."""
    seller = db.get(Seller, seller_id)
    if seller is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found.")

    today = business_today()
    if start is None and end is None:
        window_start, window_end = today - timedelta(days=29), today
    elif start is None or end is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Custom range needs both start and end dates.",
        )
    elif start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Start date must be before (or equal to) the end date.",
        )
    elif (end - start).days + 1 > 366:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Custom range can span at most one year.",
        )
    else:
        window_start, window_end = start, end

    window_days = (window_end - window_start).days + 1
    window_start_dt, _ = day_bounds_utc(window_start)
    _, window_end_dt = day_bounds_utc(window_end)
    owned = Order.seller_id == seller.id
    in_window = (Order.created_at >= window_start_dt) & (Order.created_at < window_end_dt)

    # Status counts + revenue in the window, one grouped query
    status_rows = (
        db.query(
            Order.status,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_price), 0.0),
        )
        .filter(owned, in_window)
        .group_by(Order.status)
        .all()
    )
    status_counts = {s.value: 0 for s in OrderStatus}
    total_orders = 0
    revenue = 0.0
    for row_status, count, row_total in status_rows:
        status_counts[row_status] = status_counts.get(row_status, 0) + count
        total_orders += count
        if row_status != OrderStatus.CANCELLED.value:
            revenue += float(row_total)

    # Daily buckets with revenue (business-local days, full window —
    # quiet days show as zero so the chart keeps its shape)
    day_expr = business_day(Order.created_at)
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
    daily_map = {
        str(day): (int(count), round(float(total), 2)) for day, count, total in daily_rows
    }
    daily = [
        {
            "date": (window_start + timedelta(days=i)).isoformat(),
            "count": daily_map.get((window_start + timedelta(days=i)).isoformat(), (0, 0.0))[0],
            "value": daily_map.get((window_start + timedelta(days=i)).isoformat(), (0, 0.0))[1],
        }
        for i in range(window_days)
    ]

    return {
        "store_name": seller.store_name,
        "store_slug": seller.store_slug,
        "email": seller.email,
        "plan": seller.plan,
        "plan_expires_at": seller.plan_expires_at,
        "created_at": seller.created_at,
        "range": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "total_orders": total_orders,
        "revenue": round(revenue, 2),
        "aov": round(revenue / total_orders, 2) if total_orders else 0.0,
        "status_counts": status_counts,
        "daily": daily,
    }


@router.get(
    "/sellers/{seller_id}/orders.csv",
    summary="Export one shop's orders as CSV (honors the same window as shop stats)",
)
def export_seller_orders_csv(
    seller_id: int,
    start: date | None = Query(default=None, description="Window start (YYYY-MM-DD, inclusive)"),
    end: date | None = Query(default=None, description="Window end (YYYY-MM-DD, inclusive)"),
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001 — guards access
) -> StreamingResponse:
    """Same columns as the seller's own export; scoped to the shop and
    window an admin picks on the shop-detail report."""
    seller = db.get(Seller, seller_id)
    if seller is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found.")

    today = business_today()
    if start is None and end is None:
        window_start, window_end = today - timedelta(days=29), today
    elif start is None or end is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Custom range needs both start and end dates.",
        )
    elif start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Start date must be before (or equal to) the end date.",
        )
    elif (end - start).days + 1 > 366:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Custom range can span at most one year.",
        )
    else:
        window_start, window_end = start, end

    window_start_dt, _ = day_bounds_utc(window_start)
    _, window_end_dt = day_bounds_utc(window_end)

    orders = (
        db.query(Order)
        .filter(
            Order.seller_id == seller.id,
            Order.created_at >= window_start_dt,
            Order.created_at < window_end_dt,
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )

    buffer = io.StringIO()
    # UTF-8 BOM so Excel detects the encoding (names can be Bengali)
    buffer.write("﻿")
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

    filename = f"orderkoi-{seller.store_slug}-{window_start.isoformat()}-to-{window_end.isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/upgrade-requests",
    response_model=list[AdminUpgradeRequestOut],
    summary="List Pro upgrade requests (pending first, newest first)",
)
def list_upgrade_requests(
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001 — guards access
) -> list[dict]:
    requests = (
        db.query(UpgradeRequest)
        .order_by(
            # pending first, then newest on top
            (UpgradeRequest.status != "pending").asc(),
            UpgradeRequest.created_at.desc(),
        )
        .all()
    )

    result = []
    for request in requests:
        seller = db.get(Seller, request.seller_id)
        if seller is None:
            continue  # seller deleted; the request cascaded away but be safe
        result.append(
            {
                "id": request.id,
                "months": request.months,
                "status": request.status,
                "payment_reference": request.payment_reference,
                "created_at": request.created_at,
                "handled_at": request.handled_at,
                "granted_until": request.granted_until,
                "seller_id": seller.id,
                "seller_email": seller.email,
                "store_name": seller.store_name,
                "plan": seller.plan,
                "plan_expires_at": seller.plan_expires_at,
            }
        )
    return result


@router.patch(
    "/upgrade-requests/{request_id}",
    response_model=AdminUpgradeRequestOut,
    summary="Approve or reject an upgrade request",
)
def handle_upgrade_request(
    request_id: int,
    payload: UpgradeRequestAction,
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001 — guards access
) -> dict:
    request = db.get(UpgradeRequest, request_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upgrade request not found."
        )
    if request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This request was already {request.status}.",
        )

    seller = db.get(Seller, request.seller_id)
    if seller is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Seller no longer exists."
        )

    if payload.action == "approve":
        was_pro = seller.plan == "pro"

        # Renewals stack: a still-active subscription extends from its
        # current expiry, not from today (the seller keeps paid-for time)
        now = utcnow()
        current_expiry = seller.plan_expires_at
        if (
            seller.plan == "pro"
            and current_expiry is not None
            and current_expiry > now
        ):
            base = current_expiry
        else:
            base = now

        seller.plan = "pro"
        seller.plan_expires_at = _add_months(base, request.months)

        # Freeze this approval's outcome — later renewals change the
        # seller's current expiry, but this row keeps its own result
        request.granted_until = seller.plan_expires_at

        # Ledger: first approval is a subscription, later ones renewals.
        # request_id links the event to the request that caused it, so
        # the seller's history shows the approval as ONE row.
        db.add(
            SubscriptionEvent(
                seller_id=seller.id,
                event="renewed" if was_pro else "subscribed",
                months=request.months,
                note=f"active until {seller.plan_expires_at.strftime('%d %b %Y')}",
                request_id=request.id,
            )
        )

    request.status = "approved" if payload.action == "approve" else "rejected"
    request.handled_at = utcnow()
    db.commit()
    db.refresh(seller)

    if payload.action == "approve":
        until = seller.plan_expires_at
        until_text = until.strftime("%d %b %Y") if until else "never (lifetime)"
        send_email(
            to=seller.email,
            subject=f"Your Pro plan is active — enjoy unlimited orders!",
            body=(
                "Great news — your Pro upgrade is confirmed!\n\n"
                f"Pro is active until: {until_text}\n"
                f"Duration added: {request.months} month{'s' if request.months > 1 else ''}\n\n"
                "Unlimited orders, and your customers keep ordering through "
                "your form link without limits.\n\n"
                "Thank you for supporting OrderKoi!\n"
                "— OrderKoi"
            ),
        )
    else:
        send_email(
            to=seller.email,
            subject="Your Pro upgrade request was not approved",
            body=(
                "We couldn't verify the payment for your Pro upgrade request.\n\n"
                "If you believe this is a mistake, reply to this email or "
                "double-check the bKash transaction ID and submit a new "
                "request.\n\n"
                "— OrderKoi"
            ),
        )

    return {
        "id": request.id,
        "months": request.months,
        "status": request.status,
        "payment_reference": request.payment_reference,
        "created_at": request.created_at,
        "handled_at": request.handled_at,
        "granted_until": request.granted_until,
        "seller_id": seller.id,
        "seller_email": seller.email,
        "store_name": seller.store_name,
        "plan": seller.plan,
        "plan_expires_at": seller.plan_expires_at,
    }


@router.get(
    "/subscription-events",
    response_model=list[AdminSubscriptionEventOut],
    summary="Subscription ledger — who subscribed/renewed/cancelled, and when",
)
def list_subscription_events(
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001 — guards access
) -> list[dict]:
    events = (
        db.query(SubscriptionEvent)
        .order_by(SubscriptionEvent.created_at.desc(), SubscriptionEvent.id.desc())
        .limit(200)
        .all()
    )

    result = []
    for event in events:
        seller = db.get(Seller, event.seller_id)
        if seller is None:
            continue
        result.append(
            {
                "id": event.id,
                "seller_id": seller.id,
                "event": event.event,
                "months": event.months,
                "comp": event.comp,
                "note": event.note,
                "created_at": event.created_at,
                "store_name": seller.store_name,
                "seller_email": seller.email,
            }
        )
    return result


@router.patch(
    "/sellers/{seller_id}/plan",
    response_model=AdminSellerOut,
    summary="Change a seller's subscription plan",
)
def update_seller_plan(
    seller_id: int,
    payload: PlanUpdate,
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001
) -> dict:
    seller = db.get(Seller, seller_id)
    if seller is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found.")

    # Safety: never lock yourself out of the admin panel
    if seller.role == "admin" and seller.id == admin.id and payload.plan != "pro":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admins cannot downgrade their own account's plan.",
        )

    was_pro = seller.plan == "pro"

    seller.plan = payload.plan
    if payload.plan == "pro" and payload.months is not None:
        # Duration chosen in the admin panel — same stacking rule as an
        # approved upgrade request: a still-active Pro extends from its
        # current expiry, everything else starts counting from now
        now = utcnow()
        current_expiry = seller.plan_expires_at
        if (
            was_pro
            and current_expiry is not None
            and current_expiry > now
        ):
            base = current_expiry
        else:
            base = now
        seller.plan_expires_at = _add_months(base, payload.months)
    else:
        # No duration given — honour an explicit expiry, else lifetime
        # (upgrades) or none (downgrades)
        seller.plan_expires_at = payload.plan_expires_at
    db.commit()
    db.refresh(seller)

    # Ledger: manual changes are recorded too — the audit trail stays
    # complete even when the admin flips plans by hand. Comp grants are
    # flagged so they don't count as subscription revenue.
    if payload.plan == "pro" and not was_pro:
        db.add(
            SubscriptionEvent(
                seller_id=seller.id,
                event="subscribed",
                months=payload.months,
                comp=payload.comp,
                note=(
                    f"activated manually by admin ({payload.months} month"
                    f"{'s' if payload.months > 1 else ''}"
                    + (", free" if payload.comp else "") + ")"
                    if payload.months
                    else "activated manually by admin"
                ),
            )
        )
    elif payload.plan != "pro" and was_pro:
        db.add(
            SubscriptionEvent(
                seller_id=seller.id,
                event="cancelled",
                months=None,
                note="downgraded manually by admin",
            )
        )
    elif payload.plan == "pro" and was_pro and payload.months is not None:
        db.add(
            SubscriptionEvent(
                seller_id=seller.id,
                event="renewed",
                months=payload.months,
                comp=payload.comp,
                note=(
                    f"extended manually by admin until "
                    f"{seller.plan_expires_at.strftime('%d %b %Y')}"
                ),
            )
        )
    db.commit()

    # A comp grant is a gift — tell the seller they got free Pro time
    if payload.plan == "pro" and payload.months is not None and payload.comp:
        until = seller.plan_expires_at
        until_text = until.strftime("%d %b %Y") if until else "never (lifetime)"
        send_email(
            to=seller.email,
            subject="You've received free Pro access!",
            body=(
                "Good news — the OrderKoi team has granted you Pro access "
                "for free!\n\n"
                f"Pro is active until: {until_text}\n"
                f"Duration granted: {payload.months} month"
                f"{'s' if payload.months > 1 else ''}\n\n"
                "Unlimited orders, and your customers keep ordering through "
                "your form link without limits — at no cost to you.\n\n"
                "Enjoy, and thank you for being part of OrderKoi!\n"
                "— OrderKoi"
            ),
        )

    order_stats = (
        db.query(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_price), 0.0),
        )
        .filter(Order.seller_id == seller.id, Order.status != OrderStatus.CANCELLED.value)
        .one()
    )

    return {
        **{column.name: getattr(seller, column.name) for column in Seller.__table__.columns},
        "orders_count": order_stats[0],
        "revenue": round(float(order_stats[1]), 2),
    }
