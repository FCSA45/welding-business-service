"""Add explicit security domains to knowledge bases."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_11"
down_revision: str | Sequence[str] | None = "20260812_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column("domain", sa.String(length=50), nullable=False, server_default="shared"),
    )
    op.execute(
        """
        UPDATE knowledge_bases
        SET domain = CASE
            WHEN agent_id = 'performance-report' THEN 'performance'
            WHEN agent_id = 'workshop-agent' THEN 'workshop'
            WHEN agent_id = 'inventory-agent' THEN 'inventory'
            ELSE 'shared'
        END
        """
    )
    op.create_index("ix_knowledge_bases_domain", "knowledge_bases", ["domain"])
    op.alter_column("knowledge_bases", "domain", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_knowledge_bases_domain", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "domain")
