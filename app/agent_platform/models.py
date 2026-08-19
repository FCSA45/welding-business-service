from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AgentStatus = Literal["active", "planned", "disabled"]
PermissionRole = Literal["admin", "editor", "viewer"]
ScheduleType = Literal["daily", "weekly", "monthly"]
TargetType = Literal["store_only", "wecom_chat"]
AdapterType = Literal["manual", "csv", "http_api", "database", "webhook"]


class AgentCreate(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    name: str = Field(min_length=1, max_length=200)
    group_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    system_prompt: str = Field(default="", max_length=12000)
    status: AgentStatus = "planned"
    enabled: bool = False


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    group_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    system_prompt: str | None = Field(default=None, max_length=12000)
    status: AgentStatus | None = None
    enabled: bool | None = None


class AgentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    group_name: str
    description: str
    system_prompt: str
    status: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,99}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    domain: Literal["shared", "performance", "workshop", "inventory"] = "shared"
    agent_id: str | None = None
    enabled: bool = True


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    domain: Literal["shared", "performance", "workshop", "inventory"] | None = None
    agent_id: str | None = None
    enabled: bool | None = None


class KnowledgeBaseView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str
    domain: str
    agent_id: str | None
    enabled: bool
    entry_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=50000)
    tags: str = Field(default="", max_length=500)
    metadata_json: dict = Field(default_factory=dict)
    source_type: str = Field(default="manual", min_length=1, max_length=50)
    source_ref: str = Field(default="", max_length=500)
    enabled: bool = True


class KnowledgeEntryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, min_length=1, max_length=50000)
    tags: str | None = Field(default=None, max_length=500)
    metadata_json: dict | None = None
    source_type: str | None = Field(default=None, min_length=1, max_length=50)
    source_ref: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class KnowledgeEntryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    title: str
    content: str
    tags: str
    metadata_json: dict
    source_type: str
    source_ref: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CallLogView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    agent_id: str
    channel: str
    requester_id: str
    chat_id: str | None
    question: str
    answer: str
    status: str
    error_code: str | None
    model: str
    duration_ms: int
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime


class PermissionCreate(BaseModel):
    subject_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(default="", max_length=200)
    agent_id: str | None = None
    role: PermissionRole = "viewer"
    enabled: bool = True


class PermissionUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    role: PermissionRole | None = None
    enabled: bool | None = None


class PermissionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: str
    display_name: str
    agent_id: str | None
    role: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ScheduleCreate(BaseModel):
    agent_id: str
    name: str = Field(min_length=1, max_length=200)
    schedule_type: ScheduleType
    run_time: time
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    action: str = Field(default="generate_summary", min_length=1, max_length=80)
    target_type: TargetType = "store_only"
    target_id: str = Field(default="", max_length=200)
    enabled: bool = False


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    schedule_type: ScheduleType | None = None
    run_time: time | None = None
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    action: str | None = Field(default=None, min_length=1, max_length=80)
    target_type: TargetType | None = None
    target_id: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None


class ScheduleView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    name: str
    schedule_type: str
    run_time: time
    day_of_week: int | None
    day_of_month: int | None
    action: str
    target_type: str
    target_id: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ScheduleRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_id: int
    scheduled_for: datetime
    status: str
    output: str
    error_code: str | None
    created_at: datetime


class SyncRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    read_count: int
    valid_count: int
    inserted_count: int
    duplicate_count: int
    invalid_count: int
    error_code: str | None


class DataSourceCreate(BaseModel):
    agent_id: str
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,99}$")
    name: str = Field(min_length=1, max_length=200)
    adapter_type: AdapterType
    settings_json: dict = Field(default_factory=dict)
    secret_env_key: str = Field(default="", max_length=200)
    enabled: bool = False


class DataSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    adapter_type: AdapterType | None = None
    settings_json: dict | None = None
    secret_env_key: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None


class DataSourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    code: str
    name: str
    adapter_type: str
    settings_json: dict
    secret_env_key: str
    enabled: bool
    ready: bool = False
    readiness_message: str = ""
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PlatformOverview(BaseModel):
    agent_count: int
    enabled_agent_count: int
    knowledge_base_count: int
    knowledge_entry_count: int
    call_log_count: int
    permission_count: int
    schedule_count: int
    data_source_count: int
    model_configured: bool
    model_name: str | None
    aily_configured: bool
    admin_key_configured: bool
    permission_mode: str
    scheduler_enabled: bool
