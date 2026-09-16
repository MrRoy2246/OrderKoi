"""one subscription event per upgrade request

Revision ID: d1a4c7e8f2b9
Revises: c5d9e2b3f4a6
Create Date: 2026-09-16

The ledger row written when an admin approves an upgrade request was
protected only by a check inside the endpoint ("is this request still
pending?"). Two admins clicking Approve at the same instant could both
pass that check and both write a SubscriptionEvent for the same
payment — the ledger would show the money twice and subscription
revenue would be overstated.

The endpoint now takes a row lock on the request (and on the seller),
and this index is the backstop: the database itself refuses a second
ledger row for the same request, whatever the application does.

Partial on purpose — request_id is NULL for seller cancellations and
for manual admin plan changes, which are legitimately unbounded.

The old non-unique ix_subscription_events_request_id is dropped in the
same revision: it indexes exactly the same column and would only add
write cost.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd1a4c7e8f2b9'
down_revision: Union[str, Sequence[str], None] = 'c5d9e2b3f4a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # On a database that ran the old code there may already be
    # duplicates. Check first so the failure is an explanation rather
    # than an opaque "could not create unique index". Deleting ledger
    # rows automatically would silently rewrite financial history, so
    # this stops and asks a human to decide.
    duplicates = conn.execute(
        sa.text(
            "SELECT request_id, count(*) AS n FROM subscription_events "
            "WHERE request_id IS NOT NULL "
            "GROUP BY request_id HAVING count(*) > 1 "
            "ORDER BY request_id"
        )
    ).fetchall()
    if duplicates:
        listed = "\n".join(
            f"    request {row.request_id}: {row.n} ledger rows"
            for row in duplicates
        )
        raise RuntimeError(
            "Cannot enforce one ledger row per upgrade request — these "
            f"already have more than one:\n{listed}\n\n"
            "This stops rather than deleting ledger rows, because doing "
            "that automatically would silently rewrite financial history.\n\n"
            "Resolve it by hand, then re-run `alembic upgrade head`:\n"
            "  1. Inspect the group:\n"
            "       SELECT id, seller_id, event, months, comp, note, created_at\n"
            "       FROM subscription_events WHERE request_id = <ID> ORDER BY id;\n"
            "  2. Keep the row that corresponds to the real approval and\n"
            "     clear request_id on the rest (KEEP the rows — they are\n"
            "     still real ledger entries, just not tied to that request):\n"
            "       UPDATE subscription_events SET request_id = NULL\n"
            "       WHERE request_id = <ID> AND id <> <KEEP_ID>;\n\n"
            "A fresh database has nothing to resolve and applies cleanly."
        )

    op.drop_index('ix_subscription_events_request_id', table_name='subscription_events')
    op.create_index(
        'uq_subscription_events_request_id',
        'subscription_events',
        ['request_id'],
        unique=True,
        postgresql_where=sa.text('request_id IS NOT NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_subscription_events_request_id', table_name='subscription_events')
    op.create_index(
        op.f('ix_subscription_events_request_id'),
        'subscription_events',
        ['request_id'],
        unique=False,
    )
