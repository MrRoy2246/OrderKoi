"""suspend sellers

Revision ID: 05b4f7d925a5
Revises: d1a4c7e8f2b9
Create Date: 2026-09-16

Lets an admin cut off a shop that abuses the platform, without deleting
the account. Before this there was no lever at all: the only way to stop
a fraudulent seller was to edit rows by hand.

suspended_at is nullable with no default and no constraint, which
matters operationally: adding a nullable column in PostgreSQL is a
catalogue-only change, so this migration does not rewrite or lock the
sellers table and is safe to run while the app is serving. (A NOT NULL
column with a default would have been the opposite.)

Existing rows get NULL, which is exactly the intent — every account
that already exists is active. No backfill needed.

Suspension is enforced in the application (login, get_current_seller,
and the public order endpoint), not by the database, so downgrading
this revision turns every suspended account back on. That is the right
failure direction for a downgrade: it restores access rather than
leaving accounts silently locked out with no record of why.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '05b4f7d925a5'
down_revision: Union[str, Sequence[str], None] = 'd1a4c7e8f2b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sellers',
        sa.Column('suspended_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'sellers',
        sa.Column('suspended_reason', sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sellers', 'suspended_reason')
    op.drop_column('sellers', 'suspended_at')
