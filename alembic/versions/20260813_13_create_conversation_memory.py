"""Create isolated enterprise conversation memory tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_13"
down_revision: str | Sequence[str] | None = "20260813_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("agent_id", sa.String(80), nullable=False),
        sa.Column("requester_id", sa.String(200), nullable=False),
        sa.Column("chat_id", sa.String(200), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id", "agent_id", "requester_id", "chat_id",
            name="uq_conversation_session_scope",
        ),
    )
    op.create_index(
        "ix_conversation_sessions_scope_updated", "conversation_sessions",
        ["tenant_id", "agent_id", "updated_at"],
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("external_message_id", sa.String(255)),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_redacted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sensitivity", sa.String(20), nullable=False, server_default="internal"),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "external_message_id", name="uq_conversation_message_idempotency"),
        sa.CheckConstraint("role IN ('user','assistant','system','tool')", name="ck_conversation_message_role"),
        sa.CheckConstraint("token_estimate >= 0", name="ck_conversation_message_tokens"),
    )
    op.create_index(
        "ix_conversation_messages_session_created", "conversation_messages", ["session_id", "created_at"]
    )
    op.create_table(
        "conversation_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(300), nullable=False, server_default=""),
        sa.Column("selected_entity_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result_refs_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("time_range_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", name="uq_conversation_state_session"),
        sa.CheckConstraint("state_version >= 1", name="ck_conversation_state_version"),
    )


def downgrade() -> None:
    op.drop_table("conversation_states")
    op.drop_index("ix_conversation_messages_session_created", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversation_sessions_scope_updated", table_name="conversation_sessions")
    op.drop_table("conversation_sessions")
