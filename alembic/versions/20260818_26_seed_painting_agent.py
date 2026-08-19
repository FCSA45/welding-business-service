"""Seed the isolated painting department agent.

Revision ID: 20260818_26
Revises: 20260818_25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260818_26"
down_revision: str | Sequence[str] | None = "20260818_25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    agents = sa.table(
        "agents",
        sa.column("id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("group_name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("system_prompt", sa.Text()),
        sa.column("status", sa.String()),
        sa.column("enabled", sa.Boolean()),
    )
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM agents WHERE id = :agent_id"),
        {"agent_id": "painting-agent"},
    ).scalar()
    if exists:
        return
    op.bulk_insert(agents, [{
        "id": "painting-agent",
        "name": "油漆部智能体",
        "group_name": "生产中心",
        "description": "查询油漆部订单、工序、报工与部门日常生产信息。",
        "system_prompt": (
            "你是油漆部智能体。只能依据已授权的油漆部业务数据、油漆部知识库和共享制度资料回答；"
            "数据不足时明确说明，不得编造订单、产量、进度或异常原因。"
        ),
        "status": "active",
        "enabled": True,
    }])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM agents WHERE id = 'painting-agent'"))
