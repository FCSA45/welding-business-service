"""Create daily report submissions.

Revision ID: 20260804_02
Revises: 20260731_01
Create Date: 2026-08-04
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_02"
down_revision: str | Sequence[str] | None = "20260731_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("employee_open_id", sa.String(length=128), nullable=False),
        sa.Column("employee_name", sa.String(length=200), nullable=False),
        sa.Column("completed_work", sa.Text(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("next_plan", sa.Text(), nullable=False),
        sa.Column("issues", sa.Text(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_message_id", sa.String(length=255), nullable=True),
        sa.CheckConstraint("completed_count >= 0", name="ck_daily_reports_completed_count"),
        sa.CheckConstraint("version >= 1", name="ck_daily_reports_version"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employee_open_id",
            "report_date",
            name="uq_daily_reports_employee_date",
        ),
        sa.UniqueConstraint(
            "source_message_id",
            name="uq_daily_reports_source_message_id",
        ),
    )
    op.create_index(
        "ix_daily_reports_report_date",
        "daily_reports",
        ["report_date"],
        unique=False,
    )
    op.create_index(
        "ix_daily_reports_status",
        "daily_reports",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_daily_reports_status", table_name="daily_reports")
    op.drop_index("ix_daily_reports_report_date", table_name="daily_reports")
    op.drop_table("daily_reports")
