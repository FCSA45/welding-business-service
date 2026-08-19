from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SelectedEntity(BaseModel):
    entity_type: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    entity_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(default="", max_length=300)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def reject_secret_attributes(cls, value: dict[str, Any]):
        forbidden = {"password", "secret", "token", "api_key", "private_key", "system_prompt"}
        if forbidden.intersection(key.lower() for key in value):
            raise ValueError("sensitive attributes cannot be stored in conversation state")
        return value


class ConversationTimeRange(BaseModel):
    start: datetime | None = None
    end: datetime | None = None

    @field_validator("end")
    @classmethod
    def valid_range(cls, end, info):
        start = info.data.get("start")
        if start is not None and end is not None and end < start:
            raise ValueError("end must not be earlier than start")
        return end


class ConversationStateUpdate(BaseModel):
    expected_version: int = Field(ge=0)
    topic: str = Field(default="", max_length=300)
    selected_entity: SelectedEntity | None = None
    result_refs: list[str] = Field(default_factory=list, max_length=50)
    time_range: ConversationTimeRange | None = None
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)

    @field_validator("result_refs")
    @classmethod
    def unique_refs(cls, refs: list[str]):
        cleaned = [item.strip() for item in refs if item.strip()]
        if any(len(item) > 200 for item in cleaned):
            raise ValueError("result reference is too long")
        return list(dict.fromkeys(cleaned))


class ConversationState(BaseModel):
    tenant_id: str
    agent_id: str
    requester_id: str
    chat_id: str
    topic: str = ""
    selected_entity: SelectedEntity | None = None
    result_refs: list[str] = Field(default_factory=list)
    time_range: ConversationTimeRange | None = None
    version: int = 0
    expires_at: datetime | None = None
