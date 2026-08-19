"""Add chat identifiers for conversation memory.

Revision ID: 20260810_07
Revises: 20260809_06
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260810_07"
down_revision: str | Sequence[str] | None = "20260809_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_call_logs", sa.Column("chat_id", sa.String(length=200), nullable=True))
    op.create_index("ix_agent_call_logs_chat_created", "agent_call_logs", ["chat_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_call_logs_chat_created", table_name="agent_call_logs")
    op.drop_column("agent_call_logs", "chat_id")
