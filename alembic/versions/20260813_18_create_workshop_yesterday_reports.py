"""Create versioned workshop yesterday report snapshots."""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260813_18"
down_revision: str | Sequence[str] | None = "20260811_17r"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workshop_yesterday_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="mock"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("report_date", "version", name="uq_workshop_yesterday_report_version"),
        sa.UniqueConstraint("report_date", "content_hash", name="uq_workshop_yesterday_report_content"),
        sa.CheckConstraint("version >= 1", name="ck_workshop_yesterday_report_version"),
    )
    op.create_index("ix_workshop_yesterday_reports_date", "workshop_yesterday_reports", ["report_date"])


def downgrade() -> None:
    op.drop_index("ix_workshop_yesterday_reports_date", table_name="workshop_yesterday_reports")
    op.drop_table("workshop_yesterday_reports")
