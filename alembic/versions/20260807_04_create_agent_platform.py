"""Create reusable agent platform tables.

Revision ID: 20260807_04
Revises: 20260804_03
Create Date: 2026-08-07
"""
from collections.abc import Sequence
from datetime import time

from alembic import op
import sqlalchemy as sa


revision: str = "20260807_04"
down_revision: str | Sequence[str] | None = "20260804_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("group_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_knowledge_bases_code"),
    )
    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.String(length=500), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_ref", sa.String(length=500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_entries_knowledge_base_id", "knowledge_entries", ["knowledge_base_id"])
    op.create_table(
        "agent_call_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("requester_id", sa.String(length=200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_agent_call_logs_request_id"),
    )
    op.create_index("ix_agent_call_logs_agent_created", "agent_call_logs", ["agent_id", "created_at"])
    op.create_table(
        "agent_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=True),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_id", "agent_id", name="uq_agent_permissions_subject_agent"),
    )
    op.create_table(
        "platform_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("schedule_type", sa.String(length=30), nullable=False),
        sa.Column("run_time", sa.Time(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "platform_schedule_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["schedule_id"], ["platform_schedules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_id", "scheduled_for", name="uq_schedule_runs_schedule_time"),
    )
    op.create_index("ix_schedule_runs_created_at", "platform_schedule_runs", ["created_at"])
    op.create_table(
        "data_source_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("adapter_type", sa.String(length=50), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("secret_env_key", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "code", name="uq_data_source_configs_agent_code"),
    )

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
    op.bulk_insert(
        agents,
        [
            {"id": "script-review", "name": "脚本审核员", "group_name": "新媒体运营", "description": "审核运营脚本并给出修改建议。", "system_prompt": "你是脚本审核员。仅依据提供的脚本、审核规则和知识库给出客观审核意见；资料不足时明确说明，禁止预测不存在的数据。", "status": "planned", "enabled": False},
            {"id": "performance-report", "name": "绩效检查督导", "group_name": "新媒体运营", "description": "根据日报数据生成日报、周报和月报总结。", "system_prompt": "你是绩效检查督导。只根据系统提供的日报和知识库进行总结，不编造人数、完成量、风险或排名；没有数据时明确说明暂无数据。", "status": "active", "enabled": True},
            {"id": "matrix-review", "name": "矩阵复盘专员", "group_name": "新媒体运营", "description": "复盘账号矩阵和账号状态。", "system_prompt": "你是矩阵复盘专员。只依据账号数据输出复盘结论，缺少账号数据时说明无法判断。", "status": "planned", "enabled": False},
            {"id": "content-review", "name": "内容复盘专员", "group_name": "新媒体运营", "description": "复盘内容发布效果和稳定性。", "system_prompt": "你是内容复盘专员。只根据脚本及其真实效果数据复盘，不编造曝光、播放或爆款概率。", "status": "planned", "enabled": False},
            {"id": "virtual-asset-admin", "name": "虚拟资产管理员", "group_name": "新媒体运营", "description": "管理账号、邮箱、线路等虚拟资产。", "system_prompt": "你是虚拟资产管理员。依据资产台账回答状态和风险问题，不显示未授权的敏感凭据。", "status": "planned", "enabled": False},
            {"id": "content-growth", "name": "内容营销增长专员", "group_name": "新媒体运营", "description": "分析内容到询盘和成交的转化。", "system_prompt": "你是内容营销增长专员。只根据可追溯的内容、询盘和成交数据分析转化，禁止虚构归因。", "status": "planned", "enabled": False},
            {"id": "inquiry-screening", "name": "SS询盘筛查专员", "group_name": "ERP信息管理", "description": "筛查询盘并生成有效性标签。", "system_prompt": "你是询盘筛查专员。依据对话和业务规则判断询盘标签；证据不足时标记为待确认。", "status": "planned", "enabled": False},
            {"id": "inquiry-distribution", "name": "SS询盘激活与分发专员", "group_name": "ERP信息管理", "description": "激活并按规则分发有效询盘。", "system_prompt": "你是询盘激活与分发专员。只根据有效询盘标签、业务状态和分发规则提出建议，不擅自分发。", "status": "planned", "enabled": False},
            {"id": "b2b-order-review", "name": "B端订单业绩复盘专员", "group_name": "ERP信息管理", "description": "分析询盘到B端订单成交的过程。", "system_prompt": "你是B端订单业绩复盘专员。只根据询盘、订单和成交数据复盘，不虚构客户归因。", "status": "planned", "enabled": False},
            {"id": "website-order-review", "name": "网站订单业绩复盘专员", "group_name": "ERP信息管理", "description": "分析网站访问、加购和订单数据。", "system_prompt": "你是网站订单业绩复盘专员。只根据网站统计和真实订单数据生成报告，不编造转化率。", "status": "planned", "enabled": False},
        ],
    )

    knowledge_bases = sa.table(
        "knowledge_bases",
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("agent_id", sa.String()),
        sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(
        knowledge_bases,
        [
            {"code": "common", "name": "通用知识库", "description": "所有智能体均可检索的企业通用知识。", "agent_id": None, "enabled": True},
            {"code": "performance-report", "name": "绩效检查督导知识库", "description": "日报、周报、月报的规则和常见问题。", "agent_id": "performance-report", "enabled": True},
        ],
    )

    schedules = sa.table(
        "platform_schedules",
        sa.column("agent_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("schedule_type", sa.String()),
        sa.column("run_time", sa.Time()),
        sa.column("day_of_week", sa.Integer()),
        sa.column("day_of_month", sa.Integer()),
        sa.column("action", sa.String()),
        sa.column("target_type", sa.String()),
        sa.column("target_id", sa.String()),
        sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(
        schedules,
        [{"agent_id": "performance-report", "name": "每日20点日报总结", "schedule_type": "daily", "run_time": time(hour=20), "day_of_week": None, "day_of_month": None, "action": "generate_summary", "target_type": "store_only", "target_id": "", "enabled": False}],
    )

    data_sources = sa.table(
        "data_source_configs",
        sa.column("agent_id", sa.String()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("adapter_type", sa.String()),
        sa.column("settings_json", sa.JSON()),
        sa.column("secret_env_key", sa.String()),
        sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(
        data_sources,
        [{"agent_id": "performance-report", "code": "external-daily-report", "name": "外部日报平台", "adapter_type": "http_api", "settings_json": {"status": "waiting_for_contract"}, "secret_env_key": "", "enabled": False}],
    )


def downgrade() -> None:
    op.drop_table("data_source_configs")
    op.drop_index("ix_schedule_runs_created_at", table_name="platform_schedule_runs")
    op.drop_table("platform_schedule_runs")
    op.drop_table("platform_schedules")
    op.drop_table("agent_permissions")
    op.drop_index("ix_agent_call_logs_agent_created", table_name="agent_call_logs")
    op.drop_table("agent_call_logs")
    op.drop_index("ix_knowledge_entries_knowledge_base_id", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
    op.drop_table("knowledge_bases")
    op.drop_table("agents")
