"""Create daily performance aggregates and report snapshots."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260812_10"
down_revision: str | Sequence[str] | None = "20260811_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "performance_daily_aggregates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("platform", sa.String(100), nullable=False),
        sa.Column("account_name", sa.String(200), nullable=False),
        sa.Column("operator_name", sa.String(200), nullable=False),
        sa.Column("reported_published_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_published_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("publication_difference", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reported_script_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_script_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filled_script_data_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("script_data_completeness_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("publication_agreement_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("report_date", "platform", "account_name", "operator_name", name="uq_performance_daily_dimension"),
    )
    op.create_index("ix_performance_daily_date", "performance_daily_aggregates", ["report_date"])
    op.create_table(
        "performance_report_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_type", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ready"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("feishu_message_id", sa.String(200)),
        sa.UniqueConstraint("period_type", "period_start", "period_end", "version", name="uq_performance_snapshot_version"),
    )
    op.create_index("ix_performance_snapshot_period", "performance_report_snapshots", ["period_type", "period_start", "period_end"])


def downgrade() -> None:
    op.drop_table("performance_report_snapshots")
    op.drop_table("performance_daily_aggregates")
