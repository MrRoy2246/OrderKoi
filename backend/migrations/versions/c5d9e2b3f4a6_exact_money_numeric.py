"""exact money: orders.total_price Float -> Numeric(12,2)

Revision ID: c5d9e2b3f4a6
Revises: b7e2f9a1c3d4
Create Date: 2026-09-12

Taka have exactly two decimals, and binary floats can't represent that
exactly (0.1 + 0.2 = 0.30000000000000004) — every stored total and
every SUM over the column carried drift. Numeric(12,2) stores exact
decimals; 12 digits of precision is billions of taka per order, far
beyond any real order. Existing values cast cleanly (they were always
2-decimal amounts).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d9e2b3f4a6'
down_revision: Union[str, Sequence[str], None] = 'b7e2f9a1c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'orders',
        'total_price',
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=12, scale=2),
        postgresql_using='total_price::numeric(12,2)',
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'orders',
        'total_price',
        existing_type=sa.Numeric(precision=12, scale=2),
        type_=sa.Float(),
        existing_nullable=False,
    )
