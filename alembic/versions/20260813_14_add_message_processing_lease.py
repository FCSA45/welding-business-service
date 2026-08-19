"""Add durable processing leases for crash-safe message idempotency."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_14"
down_revision: str | Sequence[str] | None = "20260813_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversation_messages", sa.Column(
        "processing_status", sa.String(20), nullable=False, server_default="completed"
    ))
    op.add_column("conversation_messages", sa.Column("lease_owner", sa.String(64)))
    op.add_column("conversation_messages", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("conversation_messages", sa.Column(
        "attempt_count", sa.Integer(), nullable=False, server_default="0"
    ))
    op.add_column("conversation_messages", sa.Column("last_error_code", sa.String(80)))
    op.add_column("conversation_messages", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_conversation_message_processing_status", "conversation_messages",
        "processing_status IN ('processing','completed','failed')",
    )
    op.create_check_constraint(
        "ck_conversation_message_attempt_count", "conversation_messages", "attempt_count >= 0"
    )
    op.create_index(
        "ix_conversation_messages_lease_recovery", "conversation_messages",
        ["processing_status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_messages_lease_recovery", table_name="conversation_messages")
    op.drop_constraint("ck_conversation_message_attempt_count", "conversation_messages", type_="check")
    op.drop_constraint("ck_conversation_message_processing_status", "conversation_messages", type_="check")
    op.drop_column("conversation_messages", "completed_at")
    op.drop_column("conversation_messages", "last_error_code")
    op.drop_column("conversation_messages", "attempt_count")
    op.drop_column("conversation_messages", "lease_expires_at")
    op.drop_column("conversation_messages", "lease_owner")
    op.drop_column("conversation_messages", "processing_status")
