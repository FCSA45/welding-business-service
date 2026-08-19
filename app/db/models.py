from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Float,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationRecordRow(Base):
    __tablename__ = "operation_records"
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_operation_records_source_hash"),
        Index("ix_operation_records_report_date", "report_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_row_id: Mapped[str | None] = mapped_column(String(255))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    platform: Mapped[str] = mapped_column(String(100), nullable=False, default="未指定平台")
    account_name: Mapped[str] = mapped_column(String(200), nullable=False, default="未指定账号")
    operator_name: Mapped[str] = mapped_column(String(200), nullable=False)
    published_count: Mapped[int] = mapped_column(Integer, nullable=False)
    script_count: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_script_data_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OperationDailyReportRow(Base):
    __tablename__ = "operation_report_entries"
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_operation_daily_reports_source_hash"),
        Index("ix_operation_daily_reports_report_date", "report_date"),
        Index("ix_operation_daily_reports_operator_name", "operator_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    platform: Mapped[str] = mapped_column(String(100), nullable=False, default="未指定平台")
    account_name: Mapped[str] = mapped_column(String(200), nullable=False, default="未指定账号")
    operator_name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    published_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_script_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    script_data_filled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_work: Mapped[str] = mapped_column(Text, nullable=False, default="")
    next_plan: Mapped[str] = mapped_column(Text, nullable=False, default="")
    issues: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_row_id: Mapped[str | None] = mapped_column(String(255))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SyncRunRow(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    read_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(50))


class PerformanceDailyAggregateRow(Base):
    __tablename__ = "performance_daily_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "report_date", "platform", "account_name", "operator_name",
            name="uq_performance_daily_dimension",
        ),
        Index("ix_performance_daily_date", "report_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reported_published_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_published_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    publication_difference: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reported_script_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_script_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filled_script_data_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    script_data_completeness_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    publication_agreement_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PerformanceReportSnapshotRow(Base):
    __tablename__ = "performance_report_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "period_type", "period_start", "period_end", "version",
            name="uq_performance_snapshot_version",
        ),
        Index("ix_performance_snapshot_period", "period_type", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ready")
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    feishu_message_id: Mapped[str | None] = mapped_column(String(200))


class DailyReportRow(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint(
            "employee_open_id",
            "report_date",
            name="uq_daily_reports_employee_date",
        ),
        UniqueConstraint(
            "source_message_id",
            name="uq_daily_reports_source_message_id",
        ),
        Index("ix_daily_reports_report_date", "report_date"),
        Index("ix_daily_reports_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    employee_open_id: Mapped[str] = mapped_column(String(128), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    completed_work: Mapped[str] = mapped_column(Text, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_plan: Mapped[str] = mapped_column(Text, nullable=False, default="")
    issues: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_message_id: Mapped[str | None] = mapped_column(String(255))


class ScheduledDeliveryRow(Base):
    __tablename__ = "scheduled_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "delivery_type",
            "delivery_date",
            name="uq_scheduled_deliveries_type_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_type: Mapped[str] = mapped_column(String(50), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgentRow(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    group_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="planned")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeBaseRow(Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (UniqueConstraint("code", name="uq_knowledge_bases_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    domain: Mapped[str] = mapped_column(String(50), nullable=False, default="shared")
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeEntryRow(Base):
    __tablename__ = "knowledge_entries"
    __table_args__ = (
        Index("ix_knowledge_entries_knowledge_base_id", "knowledge_base_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_ref: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeDocumentRow(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id", "department_code", "content_hash",
            name="uq_knowledge_documents_scope_hash",
        ),
        Index("ix_knowledge_documents_scope", "knowledge_base_id", "department_code", "enabled"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    department_code: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class KnowledgeChunkRow(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunks_document_index"),
        Index("ix_knowledge_chunks_document", "document_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_json: Mapped[list] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AgentCallLogRow(Base):
    __tablename__ = "agent_call_logs"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_agent_call_logs_request_id"),
        Index("ix_agent_call_logs_agent_created", "agent_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(200), nullable=False, default="anonymous")
    chat_id: Mapped[str | None] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConversationSessionRow(Base):
    __tablename__ = "conversation_sessions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "agent_id", "requester_id", "chat_id",
            name="uq_conversation_session_scope",
        ),
        Index("ix_conversation_sessions_scope_updated", "tenant_id", "agent_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    requester_id: Mapped[str] = mapped_column(String(200), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ConversationMessageRow(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_message_id", name="uq_conversation_message_idempotency"),
        Index("ix_conversation_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False
    )
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sensitivity: Mapped[str] = mapped_column(String(20), nullable=False, default="internal")
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConversationStateRow(Base):
    __tablename__ = "conversation_states"
    __table_args__ = (UniqueConstraint("session_id", name="uq_conversation_state_session"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    selected_entity_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    time_range_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ConversationLeaseAlertRow(Base):
    __tablename__ = "conversation_lease_alerts"
    __table_args__ = (
        UniqueConstraint("alert_key", name="uq_conversation_lease_alert_key"),
        Index("ix_conversation_lease_alerts_last_sent", "last_sent_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_key: Mapped[str] = mapped_column(String(100), nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    send_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class FeishuEventInboxRow(Base):
    __tablename__ = "feishu_event_inbox"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_feishu_event_inbox_key"),
        Index("ix_feishu_event_inbox_claim", "status", "available_at", "lease_expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(200), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgentPermissionRow(Base):
    __tablename__ = "agent_permissions"
    __table_args__ = (
        UniqueConstraint("subject_id", "agent_id", name="uq_agent_permissions_subject_agent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="viewer")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PlatformScheduleRow(Base):
    __tablename__ = "platform_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(30), nullable=False)
    run_time: Mapped[time] = mapped_column(Time, nullable=False)
    day_of_week: Mapped[int | None] = mapped_column(Integer)
    day_of_month: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(80), nullable=False, default="generate_summary")
    target_type: Mapped[str] = mapped_column(String(30), nullable=False, default="store_only")
    target_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PlatformScheduleRunRow(Base):
    __tablename__ = "platform_schedule_runs"
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_schedule_runs_schedule_time"),
        Index("ix_schedule_runs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("platform_schedules.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DataSourceConfigRow(Base):
    __tablename__ = "data_source_configs"
    __table_args__ = (
        UniqueConstraint("agent_id", "code", name="uq_data_source_configs_agent_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(50), nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    secret_env_key: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkshopDepartmentRow(Base):
    __tablename__ = "workshop_departments"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    feishu_chat_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="Asia/Shanghai")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkshopWorkOrderRow(Base):
    __tablename__ = "workshop_work_orders"
    __table_args__ = (
        CheckConstraint("planned_quantity >= 0", name="ck_workshop_order_planned_nonnegative"),
        CheckConstraint("completed_quantity >= 0", name="ck_workshop_order_completed_nonnegative"),
        CheckConstraint("completed_quantity <= planned_quantity", name="ck_workshop_order_progress_valid"),
        CheckConstraint("planned_start_at IS NULL OR planned_finish_at >= planned_start_at", name="ck_workshop_order_planned_dates"),
        CheckConstraint("actual_finish_at IS NULL OR (actual_start_at IS NOT NULL AND actual_finish_at >= actual_start_at)", name="ck_workshop_order_actual_dates"),
        Index("ix_workshop_orders_department_finish", "department_code", "planned_finish_at"),
        Index("ix_workshop_orders_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_no: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    department_code: Mapped[str] = mapped_column(ForeignKey("workshop_departments.code", ondelete="RESTRICT"), nullable=False)
    product_code: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    product_name: Mapped[str] = mapped_column(String(300), nullable=False)
    planned_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_finish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_finish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_process: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="planned")
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="mock")
    source_ref: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkshopProcessRecordRow(Base):
    __tablename__ = "workshop_process_records"
    __table_args__ = (
        UniqueConstraint("source_type", "source_record_id", "version", name="uq_workshop_process_source_version"),
        UniqueConstraint("content_hash", name="uq_workshop_process_content_hash"),
        CheckConstraint("version >= 1", name="ck_workshop_process_version_positive"),
        CheckConstraint("product_quantity >= 0", name="ck_workshop_process_quantity_nonnegative"),
        CheckConstraint("total_meters IS NULL OR total_meters >= 0", name="ck_workshop_process_meters_nonnegative"),
        CheckConstraint("total_centimeters IS NULL OR total_centimeters >= 0", name="ck_workshop_process_centimeters_nonnegative"),
        CheckConstraint("completion_rate >= 0 AND completion_rate <= 1", name="ck_workshop_process_completion_rate"),
        CheckConstraint("delivery_date >= order_date", name="ck_workshop_process_delivery_date"),
        Index("ix_workshop_process_reported", "reported_at", "process_department", "process_name"),
        Index("ix_workshop_process_pending_due", "process_status", "planned_completion_at", "delivery_date"),
        Index("ix_workshop_process_order", "product_order_no"),
        Index("ix_workshop_process_current", "source_type", "source_record_id", "is_current"),
        # Partial uniqueness is required: one current row per source record,
        # while any number of historical is_current=False versions remain valid.
        Index(
            "uq_workshop_process_current_source",
            "source_type",
            "source_record_id",
            unique=True,
            postgresql_where=text("is_current = true"),
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_record_id: Mapped[str] = mapped_column(String(100), nullable=False)
    order_code: Mapped[str] = mapped_column(String(100), nullable=False)
    product_order_no: Mapped[str] = mapped_column(String(100), nullable=False)
    picking_no: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    salesperson: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    workshop: Mapped[str] = mapped_column(String(200), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_name: Mapped[str] = mapped_column(String(300), nullable=False)
    product_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    total_meters: Mapped[float | None] = mapped_column(Float)
    total_centimeters: Mapped[float | None] = mapped_column(Float)
    color: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    process_department: Mapped[str] = mapped_column(String(200), nullable=False)
    process_name: Mapped[str] = mapped_column(String(200), nullable=False)
    process_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reporter_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")
    customer_grade: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    planned_completion_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    owner_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkshopProductionExceptionRow(Base):
    __tablename__ = "workshop_production_exceptions"
    __table_args__ = (
        CheckConstraint("resolved_at IS NULL OR resolved_at >= occurred_at", name="ck_workshop_exception_resolution_date"),
        Index("ix_workshop_exceptions_department_time", "department_code", "occurred_at"),
        Index("ix_workshop_exceptions_status_severity", "status", "severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exception_no: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    department_code: Mapped[str] = mapped_column(ForeignKey("workshop_departments.code", ondelete="RESTRICT"), nullable=False)
    work_order_no: Mapped[str | None] = mapped_column(ForeignKey("workshop_work_orders.work_order_no", ondelete="SET NULL"))
    exception_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, default="medium")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="mock")
    source_ref: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkshopDailyReportSnapshotRow(Base):
    __tablename__ = "workshop_daily_report_snapshots"
    __table_args__ = (
        UniqueConstraint("report_date", "department_code", "report_type", "version", name="uq_workshop_report_version"),
        CheckConstraint("version >= 1", name="ck_workshop_report_version_positive"),
        CheckConstraint("planned_quantity >= 0 AND completed_quantity >= 0 AND completed_quantity <= planned_quantity", name="ck_workshop_report_quantities"),
        CheckConstraint("completion_rate >= 0 AND completion_rate <= 1", name="ck_workshop_report_rate"),
        CheckConstraint("unresolved_exception_count <= exception_count", name="ck_workshop_report_exception_counts"),
        Index("ix_workshop_reports_department_date", "department_code", "report_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    department_code: Mapped[str] = mapped_column(ForeignKey("workshop_departments.code", ondelete="RESTRICT"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(30), nullable=False, default="daily")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    planned_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    active_order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_soon_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exception_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_exception_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="mock")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feishu_message_id: Mapped[str | None] = mapped_column(String(200))


class WorkshopYesterdayReportRow(Base):
    __tablename__ = "workshop_yesterday_reports"
    __table_args__ = (
        UniqueConstraint("report_date", "version", name="uq_workshop_yesterday_report_version"),
        UniqueConstraint("report_date", "content_hash", name="uq_workshop_yesterday_report_content"),
        CheckConstraint("version >= 1", name="ck_workshop_yesterday_report_version"),
        Index("ix_workshop_yesterday_reports_date", "report_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="mock")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkshopReportDeliveryRow(Base):
    """One delivery per immutable report snapshot and Feishu chat."""

    __tablename__ = "workshop_report_deliveries"
    __table_args__ = (
        UniqueConstraint("report_id", "target_chat_id", name="uq_workshop_report_delivery_target"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed')",
            name="ck_workshop_report_delivery_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_workshop_report_delivery_attempts"),
        Index("ix_workshop_report_deliveries_status", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("workshop_yesterday_reports.id", ondelete="CASCADE"), nullable=False
    )
    target_chat_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    html_path: Mapped[str | None] = mapped_column(String(500))
    image_path: Mapped[str | None] = mapped_column(String(500))
    image_key: Mapped[str | None] = mapped_column(String(300))
    feishu_message_id: Mapped[str | None] = mapped_column(String(200))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
