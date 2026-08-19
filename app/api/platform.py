from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.agent_platform.models import (
    AgentCreate,
    AgentUpdate,
    AgentView,
    CallLogView,
    DataSourceCreate,
    DataSourceUpdate,
    DataSourceView,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseView,
    KnowledgeEntryCreate,
    KnowledgeEntryUpdate,
    KnowledgeEntryView,
    PermissionCreate,
    PermissionUpdate,
    PermissionView,
    PlatformOverview,
    ScheduleCreate,
    ScheduleRunView,
    ScheduleUpdate,
    ScheduleView,
    SyncRunView,
)
from app.agent_platform.repository import (
    AgentRepository,
    CallLogRepository,
    DataSourceConfigRepository,
    KnowledgeRepository,
    PermissionRepository,
    ScheduleRepository,
    get_platform_counts,
)
from app.agent_platform.scheduler import PlatformScheduleExecutor
from app.agent_platform.service import data_source_readiness
from app.ai.gateway import ModelGatewayConfig
from app.api.dependencies import verify_admin_api_key
from app.config import Settings, get_settings
from app.db.session import get_db_session
from app.db.models import SyncRunRow
from sqlalchemy import select
from app.errors import AppError


router = APIRouter(prefix="/platform", tags=["platform"])
admin_guard = [Depends(verify_admin_api_key)]


@router.get("/overview", response_model=PlatformOverview, dependencies=admin_guard)
def get_platform_overview(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> PlatformOverview:
    counts = get_platform_counts(session)
    model_config = ModelGatewayConfig.from_settings(settings)
    return PlatformOverview(
        **counts,
        model_configured=model_config.is_configured,
        model_name=model_config.model or None,
        aily_configured=bool(settings.aily_action_api_key),
        admin_key_configured=bool(settings.platform_admin_api_key),
        permission_mode=settings.platform_permission_mode,
        scheduler_enabled=settings.platform_scheduler_enabled,
    )


@router.get("/agents", response_model=list[AgentView], dependencies=admin_guard)
def list_agents(session: Session = Depends(get_db_session)) -> list[AgentView]:
    return [AgentView.model_validate(row) for row in AgentRepository(session).list()]


@router.post("/agents", response_model=AgentView, dependencies=admin_guard)
def create_agent(request: AgentCreate, session: Session = Depends(get_db_session)) -> AgentView:
    return AgentView.model_validate(AgentRepository(session).create(request.model_dump()))


@router.patch("/agents/{agent_id}", response_model=AgentView, dependencies=admin_guard)
def update_agent(
    agent_id: str,
    request: AgentUpdate,
    session: Session = Depends(get_db_session),
) -> AgentView:
    return AgentView.model_validate(
        AgentRepository(session).update(agent_id, request.model_dump(exclude_unset=True))
    )


@router.delete("/agents/{agent_id}", dependencies=admin_guard)
def delete_agent(agent_id: str, session: Session = Depends(get_db_session)) -> dict:
    AgentRepository(session).delete(agent_id)
    return {"deleted": True}


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseView], dependencies=admin_guard)
def list_knowledge_bases(
    agent_id: str | None = None,
    session: Session = Depends(get_db_session),
) -> list[KnowledgeBaseView]:
    return [
        KnowledgeBaseView.model_validate(row).model_copy(update={"entry_count": entry_count})
        for row, entry_count in KnowledgeRepository(session).list_bases(agent_id)
    ]


@router.post("/knowledge-bases", response_model=KnowledgeBaseView, dependencies=admin_guard)
def create_knowledge_base(
    request: KnowledgeBaseCreate,
    session: Session = Depends(get_db_session),
) -> KnowledgeBaseView:
    if request.agent_id is not None:
        AgentRepository(session).require(request.agent_id)
    row = KnowledgeRepository(session).create_base(request.model_dump())
    return KnowledgeBaseView.model_validate(row)


@router.patch("/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseView, dependencies=admin_guard)
def update_knowledge_base(
    knowledge_base_id: int,
    request: KnowledgeBaseUpdate,
    session: Session = Depends(get_db_session),
) -> KnowledgeBaseView:
    changes = request.model_dump(exclude_unset=True)
    if changes.get("agent_id") is not None:
        AgentRepository(session).require(changes["agent_id"])
    row = KnowledgeRepository(session).update_base(knowledge_base_id, changes)
    return KnowledgeBaseView.model_validate(row)


@router.get("/knowledge-entries", response_model=list[KnowledgeEntryView], dependencies=admin_guard)
def list_knowledge_entries(
    knowledge_base_id: int | None = None,
    session: Session = Depends(get_db_session),
) -> list[KnowledgeEntryView]:
    return [
        KnowledgeEntryView.model_validate(row)
        for row in KnowledgeRepository(session).list_entries(knowledge_base_id)
    ]


@router.post(
    "/knowledge-bases/{knowledge_base_id}/entries",
    response_model=KnowledgeEntryView,
    dependencies=admin_guard,
)
def create_knowledge_entry(
    knowledge_base_id: int,
    request: KnowledgeEntryCreate,
    session: Session = Depends(get_db_session),
) -> KnowledgeEntryView:
    row = KnowledgeRepository(session).create_entry(knowledge_base_id, request.model_dump())
    return KnowledgeEntryView.model_validate(row)


@router.patch("/knowledge-entries/{entry_id}", response_model=KnowledgeEntryView, dependencies=admin_guard)
def update_knowledge_entry(
    entry_id: int,
    request: KnowledgeEntryUpdate,
    session: Session = Depends(get_db_session),
) -> KnowledgeEntryView:
    row = KnowledgeRepository(session).update_entry(entry_id, request.model_dump(exclude_unset=True))
    return KnowledgeEntryView.model_validate(row)


@router.delete("/knowledge-entries/{entry_id}", dependencies=admin_guard)
def delete_knowledge_entry(entry_id: int, session: Session = Depends(get_db_session)) -> dict:
    KnowledgeRepository(session).delete_entry(entry_id)
    return {"deleted": True}


@router.get("/call-logs", response_model=list[CallLogView], dependencies=admin_guard)
def list_call_logs(
    agent_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[CallLogView]:
    return [
        CallLogView.model_validate(row)
        for row in CallLogRepository(session).list(agent_id=agent_id, limit=limit)
    ]


@router.get("/permissions", response_model=list[PermissionView], dependencies=admin_guard)
def list_permissions(session: Session = Depends(get_db_session)) -> list[PermissionView]:
    return [PermissionView.model_validate(row) for row in PermissionRepository(session).list()]


@router.post("/permissions", response_model=PermissionView, dependencies=admin_guard)
def create_permission(
    request: PermissionCreate,
    session: Session = Depends(get_db_session),
) -> PermissionView:
    if request.agent_id is not None:
        AgentRepository(session).require(request.agent_id)
    return PermissionView.model_validate(PermissionRepository(session).create(request.model_dump()))


@router.patch("/permissions/{permission_id}", response_model=PermissionView, dependencies=admin_guard)
def update_permission(
    permission_id: int,
    request: PermissionUpdate,
    session: Session = Depends(get_db_session),
) -> PermissionView:
    return PermissionView.model_validate(
        PermissionRepository(session).update(permission_id, request.model_dump(exclude_unset=True))
    )


@router.delete("/permissions/{permission_id}", dependencies=admin_guard)
def delete_permission(permission_id: int, session: Session = Depends(get_db_session)) -> dict:
    PermissionRepository(session).delete(permission_id)
    return {"deleted": True}


def _validate_schedule(request: ScheduleCreate | ScheduleUpdate) -> None:
    schedule_type = request.schedule_type
    if schedule_type == "weekly" and request.day_of_week is None:
        raise AppError("INVALID_SCHEDULE", "周报任务必须设置星期", status_code=422)
    if schedule_type == "monthly" and request.day_of_month is None:
        raise AppError("INVALID_SCHEDULE", "月报任务必须设置日期", status_code=422)
    if request.target_type == "wecom_chat" and not (request.target_id or "").strip():
        raise AppError("INVALID_SCHEDULE_TARGET", "企业微信主动发送任务必须填写目标会话 ID", status_code=422)


@router.get("/schedules", response_model=list[ScheduleView], dependencies=admin_guard)
def list_schedules(session: Session = Depends(get_db_session)) -> list[ScheduleView]:
    return [ScheduleView.model_validate(row) for row in ScheduleRepository(session).list()]


@router.post("/schedules", response_model=ScheduleView, dependencies=admin_guard)
def create_schedule(
    request: ScheduleCreate,
    session: Session = Depends(get_db_session),
) -> ScheduleView:
    _validate_schedule(request)
    AgentRepository(session).require(request.agent_id)
    return ScheduleView.model_validate(ScheduleRepository(session).create(request.model_dump()))


@router.patch("/schedules/{schedule_id}", response_model=ScheduleView, dependencies=admin_guard)
def update_schedule(
    schedule_id: int,
    request: ScheduleUpdate,
    session: Session = Depends(get_db_session),
) -> ScheduleView:
    changes = request.model_dump(exclude_unset=True)
    row = ScheduleRepository(session).require(schedule_id)
    merged = ScheduleUpdate(
        schedule_type=changes.get("schedule_type", row.schedule_type),
        day_of_week=changes.get("day_of_week", row.day_of_week),
        day_of_month=changes.get("day_of_month", row.day_of_month),
    )
    _validate_schedule(merged)
    return ScheduleView.model_validate(ScheduleRepository(session).update(schedule_id, changes))


@router.delete("/schedules/{schedule_id}", dependencies=admin_guard)
def delete_schedule(schedule_id: int, session: Session = Depends(get_db_session)) -> dict:
    ScheduleRepository(session).delete(schedule_id)
    return {"deleted": True}


@router.get("/schedule-runs", response_model=list[ScheduleRunView], dependencies=admin_guard)
def list_schedule_runs(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[ScheduleRunView]:
    return [
        ScheduleRunView.model_validate(row)
        for row in ScheduleRepository(session).list_runs(limit=limit)
    ]


@router.get("/sync-runs", response_model=list[SyncRunView], dependencies=admin_guard)
def list_sync_runs(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[SyncRunView]:
    rows = session.scalars(
        select(SyncRunRow).order_by(SyncRunRow.started_at.desc()).limit(limit)
    ).all()
    return [SyncRunView.model_validate(row) for row in rows]


@router.post("/schedules/{schedule_id}/run", response_model=ScheduleRunView, dependencies=admin_guard)
def run_schedule_now(
    schedule_id: int,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ScheduleRunView:
    row = PlatformScheduleExecutor(settings, session).run(
        schedule_id,
        datetime.now(ZoneInfo(settings.app_timezone)),
    )
    return ScheduleRunView.model_validate(row)


def _data_source_view(row) -> DataSourceView:
    ready, readiness_message = data_source_readiness(
        adapter_type=row.adapter_type,
        settings_json=row.settings_json,
        secret_env_key=row.secret_env_key,
        enabled=row.enabled,
    )
    return DataSourceView.model_validate(row).model_copy(
        update={"ready": ready, "readiness_message": readiness_message}
    )


@router.get("/data-sources", response_model=list[DataSourceView], dependencies=admin_guard)
def list_data_sources(session: Session = Depends(get_db_session)) -> list[DataSourceView]:
    return [_data_source_view(row) for row in DataSourceConfigRepository(session).list()]


@router.post("/data-sources", response_model=DataSourceView, dependencies=admin_guard)
def create_data_source(
    request: DataSourceCreate,
    session: Session = Depends(get_db_session),
) -> DataSourceView:
    AgentRepository(session).require(request.agent_id)
    return _data_source_view(DataSourceConfigRepository(session).create(request.model_dump()))


@router.patch("/data-sources/{source_id}", response_model=DataSourceView, dependencies=admin_guard)
def update_data_source(
    source_id: int,
    request: DataSourceUpdate,
    session: Session = Depends(get_db_session),
) -> DataSourceView:
    row = DataSourceConfigRepository(session).update(source_id, request.model_dump(exclude_unset=True))
    return _data_source_view(row)


@router.delete("/data-sources/{source_id}", dependencies=admin_guard)
def delete_data_source(source_id: int, session: Session = Depends(get_db_session)) -> dict:
    DataSourceConfigRepository(session).delete(source_id)
    return {"deleted": True}
