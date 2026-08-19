"""Repair the knowledge domain column skipped by legacy database stamps.

Revision ID: 20260814_23
Revises: 20260814_22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_23"
down_revision: str | Sequence[str] | None = "20260814_22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("knowledge_bases")}
    if "domain" not in columns:
        op.add_column(
            "knowledge_bases",
            sa.Column("domain", sa.String(50), nullable=False, server_default="shared"),
        )
        op.execute(sa.text("""
            UPDATE knowledge_bases
            SET domain = CASE
                WHEN agent_id = 'performance-report' THEN 'performance'
                WHEN agent_id = 'workshop-agent' THEN 'workshop'
                WHEN agent_id = 'inventory-agent' THEN 'inventory'
                ELSE 'shared'
            END
        """))
        op.alter_column("knowledge_bases", "domain", server_default=None)
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("knowledge_bases")}
    if "ix_knowledge_bases_domain" not in indexes:
        op.create_index("ix_knowledge_bases_domain", "knowledge_bases", ["domain"])


def downgrade() -> None:
    pass
