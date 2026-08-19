"""Seed the workshop agent required by WeCom and workshop reports.

Revision ID: 20260814_21
Revises: 20260813_20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_21"
down_revision: str | Sequence[str] | None = "20260813_20"
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
    op.bulk_insert(agents, [{
        "id": "workshop-agent",
        "name": "车间智能体",
        "group_name": "生产车间",
        "description": "查询车间生产、工序、日报与异常信息。",
        "system_prompt": (
            "你是车间智能体。只依据系统提供的车间数据和知识库回答；"
            "资料不足时明确说明，不编造产量、进度、人员或异常原因。"
        ),
        "status": "active",
        "enabled": True,
    }])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM agents WHERE id = 'workshop-agent'"))
