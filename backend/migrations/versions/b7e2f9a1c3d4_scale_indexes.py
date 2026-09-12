"""scale indexes: time-window and per-shop ordering indexes

Revision ID: b7e2f9a1c3d4
Revises: faeac3112e6b
Create Date: 2026-09-12

Every hot query filters or sorts on a time column that had no index:
the seller's order list (ORDER BY created_at DESC per seller), the
dashboard/admin chart windows (created_at ranges), the seller
directory and recent-signups (sellers.created_at), and the
subscription ledger (created_at DESC LIMIT 200). At millions of orders
those were sequential scans on every dashboard refresh.

The composite (seller_id, created_at) index covers plain seller_id
lookups too, so the old single-column ix_orders_seller_id is dropped
in the same revision.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7e2f9a1c3d4'
down_revision: Union[str, Sequence[str], None] = 'faeac3112e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Per-shop list: filter by seller AND order by created_at in one index
    op.create_index(
        'ix_orders_seller_id_created_at', 'orders', ['seller_id', 'created_at']
    )
    # Time-window scans without a seller filter (admin/platform charts)
    op.create_index(op.f('ix_orders_created_at'), 'orders', ['created_at'])
    # Covered by the composite above — drop to halve the write cost on orders
    op.drop_index(op.f('ix_orders_seller_id'), table_name='orders')
    # Seller directory ordering + "newest signups"
    op.create_index(op.f('ix_sellers_created_at'), 'sellers', ['created_at'])
    # Subscription ledger (newest-first listing)
    op.create_index(
        op.f('ix_subscription_events_created_at'), 'subscription_events', ['created_at']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_subscription_events_created_at'), table_name='subscription_events'
    )
    op.drop_index(op.f('ix_sellers_created_at'), table_name='sellers')
    op.create_index(op.f('ix_orders_seller_id'), 'orders', ['seller_id'])
    op.drop_index(op.f('ix_orders_created_at'), table_name='orders')
    op.drop_index('ix_orders_seller_id_created_at', table_name='orders')
