"""Public order-form endpoints — no authentication required.

This is how customers place orders without any account: the seller
shares their form link (e.g. /order/abin-fashion) on their Facebook
page, the customer fills in name/phone/address/items, and the order
lands in the seller's dashboard instantly.

Prices entered by the customer are what they copied from the seller's
Facebook post — the seller reviews (and can edit) them in the
dashboard before confirming the order. The seller is notified by
email, and the customer gets a tracking code right away.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.email import send_email
from app.models import Order, OrderStatus, Seller, pro_plan_active
from app.routes.orders import (
    _compute_total,
    _generate_tracking_code,
    _initial_history,
    _insert_order_with_retry,
    _month_order_count,
)
from app.schemas import PublicOrderCreate, PublicOrderCreated, PublicStoreOut

router = APIRouter(prefix="/public/stores", tags=["public"])

settings = get_settings()


def _get_store(slug: str, db: Session) -> Seller:
    """Find the store behind a form link — 404 otherwise.

    Admin accounts are platform accounts, not shops, so they never
    have a public order form.
    """
    seller = (
        db.query(Seller)
        .filter(Seller.store_slug == slug.strip().lower())
        .first()
    )
    if seller is None or seller.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found. Check the link and try again.",
        )
    return seller


def _check_store_limit(seller: Seller, db: Session) -> None:
    """Free plan cap — phrased for the customer, not the seller."""
    if pro_plan_active(seller):
        return

    if _month_order_count(seller, db) >= settings.free_plan_monthly_orders:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This store cannot accept new orders right now. "
            "Please contact the store directly.",
        )


@router.get(
    "/{slug}",
    response_model=PublicStoreOut,
    summary="Get the store behind an order-form link (public)",
)
def get_store(slug: str, db: Session = Depends(get_db)) -> PublicStoreOut:
    seller = _get_store(slug, db)
    return PublicStoreOut(store_name=seller.store_name, slug=seller.store_slug)


@router.post(
    "/{slug}/orders",
    response_model=PublicOrderCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an order through the public form (no account needed)",
)
def submit_order(
    slug: str,
    payload: PublicOrderCreate,
    db: Session = Depends(get_db),
) -> PublicOrderCreated:
    seller = _get_store(slug, db)
    _check_store_limit(seller, db)

    items = [item.model_dump() for item in payload.items]
    total = _compute_total(items)

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
            customer_name=payload.customer_name.strip(),
            customer_phone=payload.customer_phone.strip(),
            customer_email=payload.customer_email,
            customer_address=payload.customer_address.strip(),
            items=items,
            total_price=total,
            notes=payload.notes,
            status=OrderStatus.PLACED.value,
            source="form",
            status_history=_initial_history(),
        )

    order = _insert_order_with_retry(db, build)

    _notify_seller(seller, order)

    return PublicOrderCreated(
        order_number=order.order_number,
        tracking_code=order.tracking_code,
        store_name=seller.store_name,
    )


def _notify_seller(seller: Seller, order: Order) -> None:
    """Email the seller about the new form order.

    send_email never raises by contract, but a notification problem
    must never cost the customer their order — belt and suspenders.
    """
    try:
        item_lines = "\n".join(
            f"  {item['quantity']} x {item['name']} @ Tk {item['price']:.2f}"
            for item in order.items
        )
        send_email(
            to=seller.email,
            subject=f"New order #{order.order_number} via your OrderKoi form",
            body=(
                "You have a new order!\n\n"
                f"Order #{order.order_number} — {order.customer_name} "
                f"({order.customer_phone})\n"
                f"Email: {order.customer_email or 'not provided'}\n"
                f"Address: {order.customer_address or 'not provided'}\n\n"
                f"Items:\n{item_lines}\n\n"
                f"Total: Tk {order.total_price:.2f}\n"
                f"Notes: {order.notes or 'none'}\n\n"
                f"Tracking code (share with the customer): {order.tracking_code}\n"
                f"{settings.frontend_url}/track/{order.tracking_code}\n\n"
                f"Review and confirm it in your dashboard:\n"
                f"{settings.frontend_url}/dashboard/orders/{order.id}\n\n"
                "— OrderKoi"
            ),
        )
    except Exception:  # noqa: BLE001 — logged, never propagated
        import logging

        logging.getLogger("orderkoi").exception(
            "Failed to notify seller %s about order #%s", seller.id, order.order_number
        )
