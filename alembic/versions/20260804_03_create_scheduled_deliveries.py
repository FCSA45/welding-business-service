"""Create scheduled delivery records.

Revision ID: 20260804_03
Revises: 20260804_02
Create Date: 2026-08-04
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_03"
down_revision: str | Sequence[str] | None = "20260804_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delivery_type", sa.String(length=50), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("chat_id", sa.String(length=128), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delivery_type",
            "delivery_date",
            name="uq_scheduled_deliveries_type_date",
        ),
    )


def downgrade() -> None:
    op.drop_table("scheduled_deliveries")
