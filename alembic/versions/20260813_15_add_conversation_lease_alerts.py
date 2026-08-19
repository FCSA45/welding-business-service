"""Add durable deduplication state for conversation lease alerts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_15"
down_revision: str | Sequence[str] | None = "20260813_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_lease_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_key", sa.String(100), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_payload_json", sa.JSON(), nullable=False),
        sa.Column("send_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("alert_key", name="uq_conversation_lease_alert_key"),
        sa.CheckConstraint("send_count >= 0", name="ck_conversation_lease_alert_send_count"),
    )
    op.create_index(
        "ix_conversation_lease_alerts_last_sent", "conversation_lease_alerts", ["last_sent_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_lease_alerts_last_sent", table_name="conversation_lease_alerts")
    op.drop_table("conversation_lease_alerts")
