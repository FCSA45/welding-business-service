"""Create idempotent workshop report deliveries."""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260813_19"
down_revision: str | Sequence[str] | None = "20260813_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workshop_report_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("workshop_yesterday_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_chat_id", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("html_path", sa.String(500)),
        sa.Column("image_path", sa.String(500)),
        sa.Column("image_key", sa.String(300)),
        sa.Column("feishu_message_id", sa.String(200)),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("last_error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("report_id", "target_chat_id", name="uq_workshop_report_delivery_target"),
        sa.CheckConstraint("status IN ('pending', 'sending', 'sent', 'failed')", name="ck_workshop_report_delivery_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_workshop_report_delivery_attempts"),
    )
    op.create_index("ix_workshop_report_deliveries_status", "workshop_report_deliveries", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_workshop_report_deliveries_status", table_name="workshop_report_deliveries")
    op.drop_table("workshop_report_deliveries")
