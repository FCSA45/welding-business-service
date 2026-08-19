"""Add durable inbox for fast Feishu callback acknowledgement."""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260813_16"
down_revision: str | Sequence[str] | None = "20260813_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feishu_event_inbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("message_id", sa.String(255), nullable=False),
        sa.Column("requester_id", sa.String(200), nullable=False),
        sa.Column("chat_id", sa.String(200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("lease_owner", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_key", name="uq_feishu_event_inbox_key"),
        sa.CheckConstraint("status IN ('pending','processing','completed','failed')", name="ck_feishu_event_inbox_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_feishu_event_inbox_attempts"),
    )
    op.create_index("ix_feishu_event_inbox_claim", "feishu_event_inbox", ["status", "available_at", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_feishu_event_inbox_claim", table_name="feishu_event_inbox")
    op.drop_table("feishu_event_inbox")
