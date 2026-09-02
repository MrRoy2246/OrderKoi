"""Store slug helpers — a store's public URL part.

The seller's order form lives at /order/{store_slug}, so 'Abin Fashion!'
becomes /order/abin-fashion. Slugs must be unique across the platform;
collisions are resolved with a numeric suffix (the seller's id) and,
as a last resort, a short random suffix.
"""

import re
import secrets

from sqlalchemy.orm import Session

from app.models import Seller


def slugify(value: str, suffix: str = "") -> str:
    """Make a URL-safe slug: lowercase letters/digits, dashes between words."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return f"{slug or 'store'}{suffix}"


def unique_store_slug(db: Session, store_name: str, seller_id: int | None = None) -> str:
    """Return a slug for this store name that no other seller is using."""
    base = slugify(store_name)
    candidates = [base]
    if seller_id is not None:
        candidates.append(f"{base}-{seller_id}")

    for slug in candidates:
        taken = db.query(Seller).filter(Seller.store_slug == slug).first()
        if taken is None:
            return slug

    return f"{base}-{secrets.token_hex(3)}"
