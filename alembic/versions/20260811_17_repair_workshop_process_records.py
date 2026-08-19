"""Repair deployments stamped at 20260811_17 without the workshop table."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_17r"
down_revision: str | Sequence[str] | None = "20260811_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "workshop_process_records" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "workshop_process_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_record_id", sa.String(100), nullable=False),
        sa.Column("order_code", sa.String(100), nullable=False),
        sa.Column("product_order_no", sa.String(100), nullable=False),
        sa.Column("picking_no", sa.String(100), nullable=False, server_default=""),
        sa.Column("salesperson", sa.String(200), nullable=False, server_default=""),
        sa.Column("workshop", sa.String(200), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("product_name", sa.String(300), nullable=False),
        sa.Column("product_quantity", sa.Integer(), nullable=False),
        sa.Column("total_meters", sa.Float()),
        sa.Column("total_centimeters", sa.Float()),
        sa.Column("color", sa.String(300), nullable=False, server_default=""),
        sa.Column("process_department", sa.String(200), nullable=False),
        sa.Column("process_name", sa.String(200), nullable=False),
        sa.Column("process_status", sa.String(30), nullable=False),
        sa.Column("reporter_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("reported_at", sa.DateTime(timezone=True)),
        sa.Column("completion_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("customer_grade", sa.String(20), nullable=False, server_default=""),
        sa.Column("planned_completion_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="mock"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_type", "source_record_id", name="uq_workshop_process_source_record"),
        sa.CheckConstraint("product_quantity >= 0", name="ck_workshop_process_quantity_nonnegative"),
        sa.CheckConstraint("total_meters IS NULL OR total_meters >= 0", name="ck_workshop_process_meters_nonnegative"),
        sa.CheckConstraint("total_centimeters IS NULL OR total_centimeters >= 0", name="ck_workshop_process_centimeters_nonnegative"),
        sa.CheckConstraint("completion_rate >= 0 AND completion_rate <= 1", name="ck_workshop_process_completion_rate"),
        sa.CheckConstraint("delivery_date >= order_date", name="ck_workshop_process_delivery_date"),
    )
    op.create_index("ix_workshop_process_reported", "workshop_process_records", ["reported_at", "process_department", "process_name"])
    op.create_index("ix_workshop_process_pending_due", "workshop_process_records", ["process_status", "planned_completion_at", "delivery_date"])
    op.create_index("ix_workshop_process_order", "workshop_process_records", ["product_order_no"])


def downgrade() -> None:
    # Repair migrations do not remove a table that may predate this revision.
    pass
