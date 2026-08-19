from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AgentCallLogRow,
    ConversationMessageRow,
    ConversationSessionRow,
    ConversationStateRow,
    AgentPermissionRow,
    AgentRow,
    DataSourceConfigRow,
    KnowledgeBaseRow,
    KnowledgeEntryRow,
    PlatformScheduleRow,
    PlatformScheduleRunRow,
)
from app.errors import AppError


def _apply_changes(row, changes: dict) -> None:
    for field, value in changes.items():
        setattr(row, field, value)
    if hasattr(row, "updated_at"):
        row.updated_at = datetime.now(timezone.utc)


class AgentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[AgentRow]:
        return list(self.session.scalars(select(AgentRow).order_by(AgentRow.id)).all())

    def get(self, agent_id: str) -> AgentRow | None:
        return self.session.get(AgentRow, agent_id)

    def require(self, agent_id: str) -> AgentRow:
        row = self.get(agent_id)
        if row is None:
            raise AppError("AGENT_NOT_FOUND", "智能体不存在", status_code=404)
        return row

    def create(self, values: dict) -> AgentRow:
        row = AgentRow(**values)
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError("AGENT_ALREADY_EXISTS", "智能体编号已经存在", status_code=409) from exc
        self.session.refresh(row)
        return row

    def update(self, agent_id: str, changes: dict) -> AgentRow:
        row = self.require(agent_id)
        _apply_changes(row, changes)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete(self, agent_id: str) -> None:
        row = self.require(agent_id)
        if row.enabled:
            raise AppError("AGENT_STILL_ENABLED", "请先停用智能体再删除", status_code=409)
        self.session.delete(row)
        self.session.commit()


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_bases(self, agent_id: str | None = None) -> list[tuple[KnowledgeBaseRow, int]]:
        statement = (
            select(KnowledgeBaseRow, func.count(KnowledgeEntryRow.id))
            .outerjoin(KnowledgeEntryRow, KnowledgeEntryRow.knowledge_base_id == KnowledgeBaseRow.id)
            .group_by(KnowledgeBaseRow.id)
            .order_by(KnowledgeBaseRow.agent_id.nullsfirst(), KnowledgeBaseRow.id)
        )
        if agent_id is not None:
            statement = statement.where(
                or_(KnowledgeBaseRow.agent_id == agent_id, KnowledgeBaseRow.agent_id.is_(None))
            )
        return [(row, count) for row, count in self.session.execute(statement).all()]

    def get_base(self, knowledge_base_id: int) -> KnowledgeBaseRow | None:
        return self.session.get(KnowledgeBaseRow, knowledge_base_id)

    def require_base(self, knowledge_base_id: int) -> KnowledgeBaseRow:
        row = self.get_base(knowledge_base_id)
        if row is None:
            raise AppError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在", status_code=404)
        return row

    def create_base(self, values: dict) -> KnowledgeBaseRow:
        row = KnowledgeBaseRow(**values)
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError("KNOWLEDGE_BASE_ALREADY_EXISTS", "知识库编号已经存在", status_code=409) from exc
        self.session.refresh(row)
        return row

    def update_base(self, knowledge_base_id: int, changes: dict) -> KnowledgeBaseRow:
        row = self.require_base(knowledge_base_id)
        _apply_changes(row, changes)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list_entries(self, knowledge_base_id: int | None = None) -> list[KnowledgeEntryRow]:
        statement = select(KnowledgeEntryRow)
        if knowledge_base_id is not None:
            statement = statement.where(KnowledgeEntryRow.knowledge_base_id == knowledge_base_id)
        return list(self.session.scalars(statement.order_by(KnowledgeEntryRow.updated_at.desc())).all())

    def create_entry(self, knowledge_base_id: int, values: dict) -> KnowledgeEntryRow:
        self.require_base(knowledge_base_id)
        row = KnowledgeEntryRow(knowledge_base_id=knowledge_base_id, **values)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def update_entry(self, entry_id: int, changes: dict) -> KnowledgeEntryRow:
        row = self.session.get(KnowledgeEntryRow, entry_id)
        if row is None:
            raise AppError("KNOWLEDGE_ENTRY_NOT_FOUND", "知识条目不存在", status_code=404)
        _apply_changes(row, changes)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete_entry(self, entry_id: int) -> None:
        row = self.session.get(KnowledgeEntryRow, entry_id)
        if row is None:
            raise AppError("KNOWLEDGE_ENTRY_NOT_FOUND", "知识条目不存在", status_code=404)
        self.session.delete(row)
        self.session.commit()

    def list_search_candidates(
        self,
        agent_id: str,
        domains: list[str] | None = None,
    ) -> list[tuple[KnowledgeEntryRow, KnowledgeBaseRow]]:
        statement = (
            select(KnowledgeEntryRow, KnowledgeBaseRow)
            .join(KnowledgeBaseRow, KnowledgeBaseRow.id == KnowledgeEntryRow.knowledge_base_id)
            .where(
                KnowledgeBaseRow.enabled.is_(True),
                KnowledgeEntryRow.enabled.is_(True),
                or_(KnowledgeBaseRow.agent_id == agent_id, KnowledgeBaseRow.agent_id.is_(None)),
            )
            .order_by(KnowledgeEntryRow.updated_at.desc())
            .limit(500)
        )
        if domains is not None:
            statement = statement.where(KnowledgeBaseRow.domain.in_(domains))
        return list(self.session.execute(statement).all())


class CallLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, values: dict) -> AgentCallLogRow:
        row = AgentCallLogRow(**values)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list(self, agent_id: str | None = None, limit: int = 100) -> list[AgentCallLogRow]:
        statement = select(AgentCallLogRow)
        if agent_id is not None:
            statement = statement.where(AgentCallLogRow.agent_id == agent_id)
        return list(
            self.session.scalars(
                statement.order_by(AgentCallLogRow.created_at.desc()).limit(limit)
            ).all()
        )

    def recent_context(
        self, agent_id: str, requester_id: str | None, chat_id: str | None, limit: int = 6
    ) -> list[AgentCallLogRow]:
        if not requester_id or not chat_id:
            return []
        statement = select(AgentCallLogRow).where(
            AgentCallLogRow.agent_id == agent_id,
            AgentCallLogRow.requester_id == requester_id,
            AgentCallLogRow.chat_id == chat_id,
            AgentCallLogRow.status.in_(["ok", "no_data"]),
        )
        rows = list(self.session.scalars(statement.order_by(AgentCallLogRow.created_at.desc()).limit(limit)).all())
        return list(reversed(rows))

    def latest_chat_id(self) -> str | None:
        row = self.session.scalar(
            select(AgentCallLogRow)
            .where(AgentCallLogRow.chat_id.is_not(None))
            .order_by(AgentCallLogRow.created_at.desc())
        )
        return row.chat_id if row is not None else None


class ConversationRepository:
    """All reads require the complete tenant/agent/user/chat isolation scope."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_session(
        self, *, tenant_id: str, agent_id: str, requester_id: str,
        chat_id: str, channel: str, expires_at=None,
    ) -> ConversationSessionRow:
        statement = select(ConversationSessionRow).where(
            ConversationSessionRow.tenant_id == tenant_id,
            ConversationSessionRow.agent_id == agent_id,
            ConversationSessionRow.requester_id == requester_id,
            ConversationSessionRow.chat_id == chat_id,
        )
        row = self.session.scalar(statement)
        if row is not None:
            return row
        row = ConversationSessionRow(
            tenant_id=tenant_id, agent_id=agent_id, requester_id=requester_id,
            chat_id=chat_id, channel=channel, expires_at=expires_at,
        )
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            row = self.session.scalar(statement)
            if row is None:
                raise
        self.session.refresh(row)
        return row

    def add_message(
        self, *, session_row: ConversationSessionRow, role: str, content: str,
        external_message_id: str | None = None, content_redacted: bool = False,
        sensitivity: str = "internal", token_estimate: int = 0,
        metadata_json: dict | None = None,
        processing_status: str = "completed", lease_owner: str | None = None,
        lease_expires_at=None, attempt_count: int = 0,
    ) -> ConversationMessageRow:
        if role not in {"user", "assistant", "system", "tool"}:
            raise AppError("INVALID_CONVERSATION_ROLE", "无效的会话消息角色", status_code=400)
        row = ConversationMessageRow(
            tenant_id=session_row.tenant_id, session_id=session_row.id,
            external_message_id=external_message_id, role=role, content=content,
            content_redacted=content_redacted, sensitivity=sensitivity,
            token_estimate=token_estimate, metadata_json=metadata_json or {},
            processing_status=processing_status, lease_owner=lease_owner,
            lease_expires_at=lease_expires_at, attempt_count=attempt_count,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def find_message_by_external_id(
        self, *, tenant_id: str, external_message_id: str
    ) -> ConversationMessageRow | None:
        return self.session.scalar(select(ConversationMessageRow).where(
            ConversationMessageRow.tenant_id == tenant_id,
            ConversationMessageRow.external_message_id == external_message_id,
        ))

    def claim_message(
        self, *, lease_owner: str, lease_seconds: int, **values
    ) -> tuple[ConversationMessageRow, bool]:
        """Atomically create or take over an expired/failed processing lease."""
        now = datetime.now(timezone.utc)
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        values.update(
            processing_status="processing", lease_owner=lease_owner,
            lease_expires_at=lease_expires_at, attempt_count=1,
        )
        try:
            return self.add_message(**values), True
        except IntegrityError:
            self.session.rollback()
            external_id = values.get("external_message_id")
            row = self.find_message_by_external_id(
                tenant_id=values["session_row"].tenant_id,
                external_message_id=external_id,
            ) if external_id else None
            if row is None:
                raise
            takeover = self.session.execute(
                update(ConversationMessageRow)
                .where(
                    ConversationMessageRow.id == row.id,
                    or_(
                        ConversationMessageRow.processing_status == "failed",
                        ConversationMessageRow.lease_expires_at.is_(None),
                        ConversationMessageRow.lease_expires_at <= now,
                    ),
                    ConversationMessageRow.processing_status != "completed",
                )
                .values(
                    processing_status="processing", lease_owner=lease_owner,
                    lease_expires_at=lease_expires_at,
                    attempt_count=ConversationMessageRow.attempt_count + 1,
                    last_error_code=None,
                )
                .execution_options(synchronize_session=False)
            )
            if takeover.rowcount == 1:
                self.session.commit()
                return self.session.get(ConversationMessageRow, row.id), True
            self.session.rollback()
            return self.session.get(ConversationMessageRow, row.id), False

    def complete_claim(
        self, message: ConversationMessageRow, response_payload: dict, *, lease_owner: str
    ) -> None:
        metadata = dict(message.metadata_json or {})
        metadata.update({"processing_status": "completed", "response": response_payload})
        result = self.session.execute(
            update(ConversationMessageRow)
            .where(
                ConversationMessageRow.id == message.id,
                ConversationMessageRow.processing_status == "processing",
                ConversationMessageRow.lease_owner == lease_owner,
            )
            .values(
                metadata_json=metadata, processing_status="completed",
                lease_owner=None, lease_expires_at=None,
                completed_at=datetime.now(timezone.utc), last_error_code=None,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.session.rollback()
            raise AppError(
                "MESSAGE_LEASE_LOST", "消息处理租约已失效，禁止覆盖新处理结果", status_code=409
            )
        self.session.commit()

    def fail_claim(self, message: ConversationMessageRow, error_code: str, *, lease_owner: str) -> None:
        metadata = dict(message.metadata_json or {})
        metadata.update({"processing_status": "failed", "error_code": error_code})
        result = self.session.execute(
            update(ConversationMessageRow)
            .where(
                ConversationMessageRow.id == message.id,
                ConversationMessageRow.processing_status == "processing",
                ConversationMessageRow.lease_owner == lease_owner,
            )
            .values(
                metadata_json=metadata, processing_status="failed",
                lease_owner=None, lease_expires_at=None, last_error_code=error_code,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.session.rollback()
            raise AppError("MESSAGE_LEASE_LOST", "消息处理租约已失效", status_code=409)
        self.session.commit()

    def renew_claim(
        self, *, message_id: int, lease_owner: str, lease_seconds: int
    ) -> bool:
        now = datetime.now(timezone.utc)
        result = self.session.execute(
            update(ConversationMessageRow)
            .where(
                ConversationMessageRow.id == message_id,
                ConversationMessageRow.processing_status == "processing",
                ConversationMessageRow.lease_owner == lease_owner,
                ConversationMessageRow.lease_expires_at > now,
            )
            .values(lease_expires_at=now + timedelta(seconds=lease_seconds))
            .execution_options(synchronize_session=False)
        )
        self.session.commit()
        return result.rowcount == 1

    def lease_health(self) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        row = self.session.execute(select(
            func.count().filter(ConversationMessageRow.processing_status == "processing").label("processing"),
            func.count().filter(
                ConversationMessageRow.processing_status == "processing",
                ConversationMessageRow.lease_expires_at <= now,
            ).label("expired"),
            func.count().filter(ConversationMessageRow.processing_status == "failed").label("failed"),
            func.count().filter(ConversationMessageRow.attempt_count > 1).label("retried"),
            func.max(ConversationMessageRow.attempt_count).label("max_attempts"),
        )).one()
        return {key: int(getattr(row, key) or 0) for key in (
            "processing", "expired", "failed", "retried", "max_attempts"
        )}

    def recent_messages(
        self, *, tenant_id: str, agent_id: str, requester_id: str,
        chat_id: str, limit: int = 12,
    ) -> list[ConversationMessageRow]:
        statement = (
            select(ConversationMessageRow)
            .join(ConversationSessionRow, ConversationSessionRow.id == ConversationMessageRow.session_id)
            .where(
                ConversationSessionRow.tenant_id == tenant_id,
                ConversationSessionRow.agent_id == agent_id,
                ConversationSessionRow.requester_id == requester_id,
                ConversationSessionRow.chat_id == chat_id,
                ConversationSessionRow.status == "active",
            )
            .order_by(ConversationMessageRow.created_at.desc(), ConversationMessageRow.id.desc())
            .limit(limit)
        )
        return list(reversed(self.session.scalars(statement).all()))

    def _state_scope_statement(
        self, *, tenant_id: str, agent_id: str, requester_id: str, chat_id: str
    ):
        return (
            select(ConversationStateRow)
            .join(ConversationSessionRow, ConversationSessionRow.id == ConversationStateRow.session_id)
            .where(
                ConversationStateRow.tenant_id == tenant_id,
                ConversationSessionRow.tenant_id == tenant_id,
                ConversationSessionRow.agent_id == agent_id,
                ConversationSessionRow.requester_id == requester_id,
                ConversationSessionRow.chat_id == chat_id,
            )
        )

    def get_state(
        self, *, tenant_id: str, agent_id: str, requester_id: str, chat_id: str
    ) -> ConversationStateRow | None:
        return self.session.scalar(self._state_scope_statement(
            tenant_id=tenant_id, agent_id=agent_id,
            requester_id=requester_id, chat_id=chat_id,
        ))

    def save_state(
        self, *, session_row: ConversationSessionRow, expected_version: int,
        topic: str, selected_entity_json: dict, result_refs_json: list,
        time_range_json: dict, expires_at,
    ) -> ConversationStateRow:
        if expected_version == 0:
            row = ConversationStateRow(
                tenant_id=session_row.tenant_id, session_id=session_row.id,
                topic=topic, selected_entity_json=selected_entity_json,
                result_refs_json=result_refs_json, time_range_json=time_range_json,
                state_version=1, expires_at=expires_at,
            )
            self.session.add(row)
            try:
                self.session.commit()
            except IntegrityError as exc:
                self.session.rollback()
                raise AppError(
                    "CONVERSATION_STATE_VERSION_CONFLICT",
                    "会话状态已被其他请求更新，请重新读取后再试",
                    status_code=409,
                ) from exc
            self.session.refresh(row)
            return row

        statement = (
            update(ConversationStateRow)
            .where(
                ConversationStateRow.session_id == session_row.id,
                ConversationStateRow.tenant_id == session_row.tenant_id,
                ConversationStateRow.state_version == expected_version,
            )
            .values(
                topic=topic, selected_entity_json=selected_entity_json,
                result_refs_json=result_refs_json, time_range_json=time_range_json,
                state_version=expected_version + 1, expires_at=expires_at,
                updated_at=datetime.now(timezone.utc),
            )
        )
        result = self.session.execute(statement)
        if result.rowcount != 1:
            self.session.rollback()
            raise AppError(
                "CONVERSATION_STATE_VERSION_CONFLICT",
                "会话状态已被其他请求更新，请重新读取后再试",
                status_code=409,
            )
        self.session.commit()
        return self.session.scalar(
            select(ConversationStateRow).where(ConversationStateRow.session_id == session_row.id)
        )

    def clear_state(
        self, *, tenant_id: str, agent_id: str, requester_id: str, chat_id: str
    ) -> None:
        state = self.get_state(
            tenant_id=tenant_id, agent_id=agent_id,
            requester_id=requester_id, chat_id=chat_id,
        )
        if state is not None:
            self.session.execute(delete(ConversationStateRow).where(ConversationStateRow.id == state.id))
            self.session.commit()


class PermissionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[AgentPermissionRow]:
        return list(
            self.session.scalars(
                select(AgentPermissionRow).order_by(
                    AgentPermissionRow.subject_id,
                    AgentPermissionRow.agent_id.nullsfirst(),
                )
            ).all()
        )

    def find(self, subject_id: str, agent_id: str) -> AgentPermissionRow | None:
        statement = (
            select(AgentPermissionRow)
            .where(
                AgentPermissionRow.subject_id == subject_id,
                AgentPermissionRow.enabled.is_(True),
                or_(AgentPermissionRow.agent_id == agent_id, AgentPermissionRow.agent_id.is_(None)),
            )
            .order_by(AgentPermissionRow.agent_id.desc().nullslast())
        )
        return self.session.scalar(statement)

    def create(self, values: dict) -> AgentPermissionRow:
        statement = select(AgentPermissionRow).where(
            AgentPermissionRow.subject_id == values["subject_id"],
            AgentPermissionRow.agent_id.is_(None)
            if values.get("agent_id") is None
            else AgentPermissionRow.agent_id == values["agent_id"],
        )
        if self.session.scalar(statement) is not None:
            raise AppError("PERMISSION_ALREADY_EXISTS", "该用户权限已经存在", status_code=409)
        row = AgentPermissionRow(**values)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def update(self, permission_id: int, changes: dict) -> AgentPermissionRow:
        row = self.session.get(AgentPermissionRow, permission_id)
        if row is None:
            raise AppError("PERMISSION_NOT_FOUND", "权限记录不存在", status_code=404)
        _apply_changes(row, changes)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete(self, permission_id: int) -> None:
        row = self.session.get(AgentPermissionRow, permission_id)
        if row is None:
            raise AppError("PERMISSION_NOT_FOUND", "权限记录不存在", status_code=404)
        self.session.delete(row)
        self.session.commit()


class ScheduleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[PlatformScheduleRow]:
        return list(self.session.scalars(select(PlatformScheduleRow).order_by(PlatformScheduleRow.id)).all())

    def list_enabled(self) -> list[PlatformScheduleRow]:
        return list(
            self.session.scalars(
                select(PlatformScheduleRow)
                .where(PlatformScheduleRow.enabled.is_(True))
                .order_by(PlatformScheduleRow.id)
            ).all()
        )

    def require(self, schedule_id: int) -> PlatformScheduleRow:
        row = self.session.get(PlatformScheduleRow, schedule_id)
        if row is None:
            raise AppError("SCHEDULE_NOT_FOUND", "定时任务不存在", status_code=404)
        return row

    def create(self, values: dict) -> PlatformScheduleRow:
        row = PlatformScheduleRow(**values)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def update(self, schedule_id: int, changes: dict) -> PlatformScheduleRow:
        row = self.require(schedule_id)
        _apply_changes(row, changes)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete(self, schedule_id: int) -> None:
        row = self.require(schedule_id)
        self.session.delete(row)
        self.session.commit()

    def already_ran(self, schedule_id: int, scheduled_for: datetime) -> bool:
        return self.session.scalar(
            select(PlatformScheduleRunRow.id).where(
                PlatformScheduleRunRow.schedule_id == schedule_id,
                PlatformScheduleRunRow.scheduled_for == scheduled_for,
            )
        ) is not None

    def create_run(self, values: dict) -> PlatformScheduleRunRow:
        row = PlatformScheduleRunRow(**values)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list_runs(self, limit: int = 100) -> list[PlatformScheduleRunRow]:
        return list(
            self.session.scalars(
                select(PlatformScheduleRunRow)
                .order_by(PlatformScheduleRunRow.created_at.desc())
                .limit(limit)
            ).all()
        )


class DataSourceConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[DataSourceConfigRow]:
        return list(self.session.scalars(select(DataSourceConfigRow).order_by(DataSourceConfigRow.id)).all())

    def require(self, source_id: int) -> DataSourceConfigRow:
        row = self.session.get(DataSourceConfigRow, source_id)
        if row is None:
            raise AppError("DATA_SOURCE_NOT_FOUND", "数据源配置不存在", status_code=404)
        return row

    def create(self, values: dict) -> DataSourceConfigRow:
        row = DataSourceConfigRow(**values)
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError("DATA_SOURCE_ALREADY_EXISTS", "该智能体的数据源编号已经存在", status_code=409) from exc
        self.session.refresh(row)
        return row

    def update(self, source_id: int, changes: dict) -> DataSourceConfigRow:
        row = self.require(source_id)
        _apply_changes(row, changes)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete(self, source_id: int) -> None:
        row = self.require(source_id)
        self.session.delete(row)
        self.session.commit()


def get_platform_counts(session: Session) -> dict[str, int]:
    return {
        "agent_count": session.scalar(select(func.count()).select_from(AgentRow)) or 0,
        "enabled_agent_count": session.scalar(
            select(func.count()).select_from(AgentRow).where(AgentRow.enabled.is_(True))
        ) or 0,
        "knowledge_base_count": session.scalar(select(func.count()).select_from(KnowledgeBaseRow)) or 0,
        "knowledge_entry_count": session.scalar(select(func.count()).select_from(KnowledgeEntryRow)) or 0,
        "call_log_count": session.scalar(select(func.count()).select_from(AgentCallLogRow)) or 0,
        "permission_count": session.scalar(select(func.count()).select_from(AgentPermissionRow)) or 0,
        "schedule_count": session.scalar(select(func.count()).select_from(PlatformScheduleRow)) or 0,
        "data_source_count": session.scalar(select(func.count()).select_from(DataSourceConfigRow)) or 0,
    }
