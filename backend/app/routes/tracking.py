"""Public tracking endpoint — no authentication required.

This is what customers hit from the link a seller shares.
Carefully shaped responses: only non-sensitive fields.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, Seller
from app.schemas import TrackingOut

router = APIRouter(prefix="/track", tags=["tracking"])


@router.get(
    "/{tracking_code}",
    response_model=TrackingOut,
    summary="Track an order by its code (public)",
)
def track_order(tracking_code: str, db: Session = Depends(get_db)) -> TrackingOut:
    # Normalize: codes are stored uppercase; tolerate lowercase input
    order = (
        db.query(Order)
        .filter(Order.tracking_code == tracking_code.strip().upper())
        .first()
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found. Check the tracking code and try again.",
        )

    seller = db.get(Seller, order.seller_id)

    # Explicit construction — the public contract stays obvious
    # and can never accidentally include a sensitive field.
    return TrackingOut(
        store_name=seller.store_name if seller else "Store",
        order_number=order.order_number,
        customer_name=order.customer_name,
        status=order.status,
        status_history=order.status_history,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )
