"""Create workshop department, work order, exception and report tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260813_12"
down_revision: str | Sequence[str] | None = "20260813_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workshop_departments",
        sa.Column("code", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("feishu_chat_id", sa.String(200), nullable=False, server_default=""),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "workshop_work_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_order_no", sa.String(100), nullable=False, unique=True),
        sa.Column("department_code", sa.String(50), nullable=False),
        sa.Column("product_code", sa.String(100), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(300), nullable=False),
        sa.Column("planned_quantity", sa.Integer(), nullable=False),
        sa.Column("completed_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("planned_start_at", sa.DateTime(timezone=True)),
        sa.Column("planned_finish_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_start_at", sa.DateTime(timezone=True)),
        sa.Column("actual_finish_at", sa.DateTime(timezone=True)),
        sa.Column("current_process", sa.String(200), nullable=False, server_default=""),
        sa.Column("status", sa.String(30), nullable=False, server_default="planned"),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="mock"),
        sa.Column("source_ref", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["department_code"], ["workshop_departments.code"], ondelete="RESTRICT"),
        sa.CheckConstraint("planned_quantity >= 0", name="ck_workshop_order_planned_nonnegative"),
        sa.CheckConstraint("completed_quantity >= 0", name="ck_workshop_order_completed_nonnegative"),
        sa.CheckConstraint("completed_quantity <= planned_quantity", name="ck_workshop_order_progress_valid"),
        sa.CheckConstraint("planned_start_at IS NULL OR planned_finish_at >= planned_start_at", name="ck_workshop_order_planned_dates"),
        sa.CheckConstraint("actual_finish_at IS NULL OR (actual_start_at IS NOT NULL AND actual_finish_at >= actual_start_at)", name="ck_workshop_order_actual_dates"),
    )
    op.create_index("ix_workshop_orders_department_finish", "workshop_work_orders", ["department_code", "planned_finish_at"])
    op.create_index("ix_workshop_orders_status", "workshop_work_orders", ["status"])
    op.create_table(
        "workshop_production_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exception_no", sa.String(100), nullable=False, unique=True),
        sa.Column("department_code", sa.String(50), nullable=False),
        sa.Column("work_order_no", sa.String(100)),
        sa.Column("exception_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False, server_default="medium"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("owner", sa.String(200), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="mock"),
        sa.Column("source_ref", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["department_code"], ["workshop_departments.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["work_order_no"], ["workshop_work_orders.work_order_no"], ondelete="SET NULL"),
        sa.CheckConstraint("resolved_at IS NULL OR resolved_at >= occurred_at", name="ck_workshop_exception_resolution_date"),
    )
    op.create_index("ix_workshop_exceptions_department_time", "workshop_production_exceptions", ["department_code", "occurred_at"])
    op.create_index("ix_workshop_exceptions_status_severity", "workshop_production_exceptions", ["status", "severity"])
    op.create_table(
        "workshop_daily_report_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("department_code", sa.String(50), nullable=False),
        sa.Column("report_type", sa.String(30), nullable=False, server_default="daily"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("planned_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active_order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_soon_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overdue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exception_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unresolved_exception_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="mock"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("feishu_message_id", sa.String(200)),
        sa.ForeignKeyConstraint(["department_code"], ["workshop_departments.code"], ondelete="RESTRICT"),
        sa.UniqueConstraint("report_date", "department_code", "report_type", "version", name="uq_workshop_report_version"),
        sa.CheckConstraint("version >= 1", name="ck_workshop_report_version_positive"),
        sa.CheckConstraint("planned_quantity >= 0 AND completed_quantity >= 0 AND completed_quantity <= planned_quantity", name="ck_workshop_report_quantities"),
        sa.CheckConstraint("completion_rate >= 0 AND completion_rate <= 1", name="ck_workshop_report_rate"),
        sa.CheckConstraint("unresolved_exception_count <= exception_count", name="ck_workshop_report_exception_counts"),
    )
    op.create_index("ix_workshop_reports_department_date", "workshop_daily_report_snapshots", ["department_code", "report_date"])


def downgrade() -> None:
    op.drop_index("ix_workshop_reports_department_date", table_name="workshop_daily_report_snapshots")
    op.drop_table("workshop_daily_report_snapshots")
    op.drop_index("ix_workshop_exceptions_status_severity", table_name="workshop_production_exceptions")
    op.drop_index("ix_workshop_exceptions_department_time", table_name="workshop_production_exceptions")
    op.drop_table("workshop_production_exceptions")
    op.drop_index("ix_workshop_orders_status", table_name="workshop_work_orders")
    op.drop_index("ix_workshop_orders_department_finish", table_name="workshop_work_orders")
    op.drop_table("workshop_work_orders")
    op.drop_table("workshop_departments")
