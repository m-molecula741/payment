"""payment claim and webhook delivery timestamps

Revision ID: 0002_payment_claims
Revises: 0001_payments_outbox
Create Date: 2026-11-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_payment_claims"
down_revision: str | Sequence[str] | None = "0001_payments_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "payments",
        sa.Column("webhook_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("webhook_delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "webhook_delivered_at")
    op.drop_column("payments", "webhook_claimed_at")
    op.drop_column("payments", "claimed_at")
