"""Create advertising-signage operation daily reports.

Revision ID: 20260809_06
Revises: 20260809_05
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260809_06"
down_revision: str | Sequence[str] | None = "20260809_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_daily_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("operator_name", sa.String(length=200), nullable=False),
        sa.Column("project_name", sa.String(length=300), nullable=False),
        sa.Column("published_count", sa.Integer(), nullable=False),
        sa.Column("submitted_script_count", sa.Integer(), nullable=False),
        sa.Column("script_data_filled_count", sa.Integer(), nullable=False),
        sa.Column("completed_work", sa.Text(), nullable=False),
        sa.Column("next_plan", sa.Text(), nullable=False),
        sa.Column("issues", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_row_id", sa.String(length=255), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_hash", name="uq_operation_daily_reports_source_hash"),
    )
    op.create_index("ix_operation_daily_reports_report_date", "operation_daily_reports", ["report_date"])
    op.create_index("ix_operation_daily_reports_operator_name", "operation_daily_reports", ["operator_name"])


def downgrade() -> None:
    op.drop_index("ix_operation_daily_reports_operator_name", table_name="operation_daily_reports")
    op.drop_index("ix_operation_daily_reports_report_date", table_name="operation_daily_reports")
    op.drop_table("operation_daily_reports")
