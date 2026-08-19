"""Create operational report entries and enrich platform records."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260811_09"
down_revision: str | Sequence[str] | None = "20260810_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("operation_records", sa.Column("platform", sa.String(100), nullable=False, server_default="未指定平台"))
    op.add_column("operation_records", sa.Column("account_name", sa.String(200), nullable=False, server_default="未指定账号"))
    op.add_column("operation_records", sa.Column("filled_script_data_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_operation_records_match", "operation_records", ["report_date", "platform", "account_name", "operator_name"])

    op.create_table(
        "operation_report_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("platform", sa.String(100), nullable=False),
        sa.Column("account_name", sa.String(200), nullable=False),
        sa.Column("operator_name", sa.String(200), nullable=False),
        sa.Column("project_name", sa.String(300), nullable=False, server_default=""),
        sa.Column("published_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_script_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("script_data_filled_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_work", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_plan", sa.Text(), nullable=False, server_default=""),
        sa.Column("issues", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("source_row_id", sa.String(255)),
        sa.Column("source_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_operation_report_entries_match", "operation_report_entries", ["report_date", "platform", "account_name", "operator_name"])


def downgrade() -> None:
    op.drop_table("operation_report_entries")
    op.drop_index("ix_operation_records_match", table_name="operation_records")
    op.drop_column("operation_records", "filled_script_data_count")
    op.drop_column("operation_records", "account_name")
    op.drop_column("operation_records", "platform")
