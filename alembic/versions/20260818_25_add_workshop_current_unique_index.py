"""Prevent multiple current workshop process versions per source record."""

from alembic import op
import sqlalchemy as sa


revision = "20260818_25"
down_revision = "20260816_24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A plain UNIQUE(source_type, source_record_id, is_current) would also
    # prohibit multiple historical False rows. The partial unique index keeps
    # history and enforces the actual invariant: only one True row.
    op.create_index(
        "uq_workshop_process_current_source",
        "workshop_process_records",
        ["source_type", "source_record_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
        sqlite_where=sa.text("is_current = 1"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_workshop_process_current_source",
        table_name="workshop_process_records",
    )
