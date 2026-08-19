"""Add metadata fields to knowledge entries.

Revision ID: 20260809_05
Revises: 20260807_04
Create Date: 2026-08-09
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260809_05"
down_revision: str | Sequence[str] | None = "20260807_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep this migration repeatable for databases that received these fields
    # during an earlier manual setup or an interrupted migration.
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("knowledge_entries")}

    if "tags" not in columns:
        op.add_column(
            "knowledge_entries",
            sa.Column("tags", sa.String(length=500), nullable=False, server_default=""),
        )
        op.alter_column("knowledge_entries", "tags", server_default=None)

    if "metadata_json" not in columns:
        op.add_column(
            "knowledge_entries",
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        )
        op.alter_column("knowledge_entries", "metadata_json", server_default=None)


def downgrade() -> None:
    op.drop_column("knowledge_entries", "metadata_json")
    op.drop_column("knowledge_entries", "tags")
