"""Admin endpoints — the platform owner's view of the business.

Admin-only: see every seller, who subscribed (Pro) vs free,
platform-wide stats, manage subscription plans, and approve or reject
Pro upgrade requests (the seller pays via bKash/Nagad first, then the
admin verifies the payment and activates the paid-for duration).
"""

import calendar
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
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
    as_aware,
    pro_plan_active,
    utcnow,
)
from app.schemas import (
    AdminSellerOut,
    AdminStatsOut,
    AdminSubscriptionEventOut,
    AdminUpgradeRequestOut,
    MonthCount,
    MonthValue,
    DailyCount,
    PlanUpdate,
    PRO_PRICES,
    RecentSignupOut,
    UpgradeRequestAction,
)
from app.timezone import (
    business_now,
    business_today,
    business_tz,
    month_start_utc,
    sqlite_shift_modifiers,
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


def _subscription_revenue(db: Session, since: datetime | None = None) -> float:
    """Total money sellers paid for Pro — comp (free) grants excluded.

    Each paid ledger entry's months map to a price from PRO_PRICES;
    entries with an unknown duration (data oddities) contribute nothing.
    `since` (UTC, naive — how ledger timestamps are stored) limits the
    sum to recent entries, e.g. the 30-day pulse.
    """
    query = db.query(SubscriptionEvent.months).filter(
        SubscriptionEvent.event.in_(["subscribed", "renewed"]),
        SubscriptionEvent.comp.is_(False),
        SubscriptionEvent.months.isnot(None),
    )
    if since is not None:
        query = query.filter(SubscriptionEvent.created_at >= since)
    return float(sum(PRO_PRICES.get(months, 0) for (months,) in query.all()))


@router.get(
    "/sellers",
    response_model=list[AdminSellerOut],
    summary="List all sellers with usage stats",
)
def list_sellers(
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001 — guards access
) -> list[dict]:
    # Orders + revenue per seller in one grouped query
    order_stats = {
        seller_id: (int(count), float(revenue))
        for seller_id, count, revenue in db.query(
            Order.seller_id,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_price), 0.0),
        )
        .filter(Order.status != OrderStatus.CANCELLED.value)
        .group_by(Order.seller_id)
        .all()
    }

    sellers = db.query(Seller).order_by(Seller.created_at.desc()).all()
    return [
        {
            **{column.name: getattr(seller, column.name) for column in Seller.__table__.columns},
            "orders_count": order_stats.get(seller.id, (0, 0.0))[0],
            "revenue": round(order_stats.get(seller.id, (0, 0.0))[1], 2),
        }
        for seller in sellers
    ]


@router.get(
    "/stats",
    response_model=AdminStatsOut,
    summary="Platform-wide statistics",
)
def platform_stats(
    db: Session = Depends(get_db),
    admin: Seller = Depends(get_current_admin),  # noqa: ARG001
) -> dict:
    sellers = db.query(Seller).all()
    seller_ids = [seller.id for seller in sellers]

    total_orders = 0
    platform_revenue = 0.0
    sellers_with_orders = 0

    if seller_ids:
        rows = (
            db.query(
                Order.seller_id,
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_price), 0.0),
            )
            .filter(Order.status != OrderStatus.CANCELLED.value)
            .group_by(Order.seller_id)
            .all()
        )
        total_orders = sum(count for _sid, count, _rev in rows)
        platform_revenue = round(sum(float(rev) for _sid, _count, rev in rows), 2)
        sellers_with_orders = len(rows)

    # "Seller" accounts only — admins aren't counted as shops
    shops = [seller for seller in sellers if seller.role == "seller"]
    pending_upgrades = (
        db.query(func.count(UpgradeRequest.id))
        .filter(UpgradeRequest.status == "pending")
        .scalar()
    )

    # Growth pulse — this business month and the last 30 days.
    # Same window conventions as the seller stats (Asia/Dhaka days).
    month_start = month_start_utc()
    # Rolling 30-day window — aware, because as_aware() comparisons below
    # need both sides aware (naive-vs-aware raises TypeError)
    thirty_days_ago = utcnow() - timedelta(days=30)

    if shops:
        month_rows = (
            db.query(
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_price), 0.0),
            )
            .filter(
                Order.seller_id.in_([s.id for s in shops]),
                Order.created_at >= month_start,
                Order.status != OrderStatus.CANCELLED.value,
            )
            .one()
        )
        orders_this_month = int(month_rows[0])
        gmv_this_month = round(float(month_rows[1]), 2)
        new_sellers_30d = sum(
            1 for s in shops if as_aware(s.created_at) >= thirty_days_ago
        )
    else:
        orders_this_month, gmv_this_month, new_sellers_30d = 0, 0.0, 0

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
    # (comp grants don't count). `since` must be naive UTC to compare
    # against the stored ledger timestamps.
    subscription_revenue_total = _subscription_revenue(db)
    subscription_revenue_30d = _subscription_revenue(
        db, since=utcnow().replace(tzinfo=None) - timedelta(days=30)
    )

    # ---- Chart series (business-timezone buckets, oldest first) ----

    # Orders per day, last 30 days
    day_expr = func.date(Order.created_at, *sqlite_shift_modifiers())
    daily_rows = (
        db.query(
            day_expr,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_price), 0.0),
        )
        .filter(
            Order.created_at >= utcnow() - timedelta(days=30),
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
            date=(business_today() - timedelta(days=29 - i)).isoformat(),
            count=daily_map.get((business_today() - timedelta(days=29 - i)).isoformat(), (0, 0.0))[0],
        )
        for i in range(30)
    ]

    # Month buckets for GMV + signups: group by business-local YYYY-MM.
    # Keys come from plain (year, month) arithmetic on the *local* date —
    # UTC-space month arithmetic drifts by the tz offset (Dhaka +6) and
    # produces duplicate or skipped months.
    month_expr = func.strftime("%Y-%m", Order.created_at, *sqlite_shift_modifiers())
    now_local = business_now()
    month_index = now_local.year * 12 + (now_local.month - 1) - 11  # 11 months back
    back_year, back_month = divmod(month_index, 12)
    first_bucket_start = (
        datetime(back_year, back_month + 1, 1, tzinfo=business_tz)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
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
        str(month): (int(count), round(float(total), 2)) for month, count, total in gmv_rows
    }

    seller_month_expr = func.strftime("%Y-%m", Seller.created_at, *sqlite_shift_modifiers())
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

    # Build the last 12 business months, oldest first
    months_series = []
    cursor = month_index
    for _i in range(12):
        year, month0 = divmod(cursor, 12)
        key = f"{year:04d}-{month0 + 1:02d}"
        count, value = gmv_map.get(key, (0, 0.0))
        months_series.append(MonthValue(month=key, count=count, value=value))
        cursor += 1
    revenue_monthly = months_series
    sellers_monthly = [
        MonthCount(month=m.month, count=signup_map.get(m.month, 0)) for m in months_series
    ]

    return {
        "total_sellers": len(shops),
        "pro_sellers": sum(1 for seller in shops if pro_plan_active(seller)),
        "free_sellers": sum(1 for seller in shops if not pro_plan_active(seller)),
        "sellers_with_orders": sellers_with_orders,
        "total_orders": total_orders,
        "platform_revenue": platform_revenue,
        "pending_upgrade_requests": pending_upgrades,
        "orders_this_month": orders_this_month,
        "gmv_this_month": gmv_this_month,
        "new_sellers_30d": new_sellers_30d,
        "recent_signups": recent_signups,
        "subscription_revenue_total": round(subscription_revenue_total, 2),
        "subscription_revenue_30d": round(subscription_revenue_30d, 2),
        "orders_daily": orders_daily,
        "revenue_monthly": revenue_monthly,
        "sellers_monthly": sellers_monthly,
    }


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
            and as_aware(current_expiry) > now
        ):
            base = current_expiry
        else:
            base = now

        seller.plan = "pro"
        seller.plan_expires_at = _add_months(base, request.months)

        # Freeze this approval's outcome — later renewals change the
        # seller's current expiry, but this row keeps its own result
        request.granted_until = seller.plan_expires_at

        # Ledger: first approval is a subscription, later ones renewals
        db.add(
            SubscriptionEvent(
                seller_id=seller.id,
                event="renewed" if was_pro else "subscribed",
                months=request.months,
                note=f"active until {seller.plan_expires_at.strftime('%d %b %Y')}",
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
                "double-check the bKash/Nagad transaction ID and submit a new "
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
            and as_aware(current_expiry) > now
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
