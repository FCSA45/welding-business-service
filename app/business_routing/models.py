from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequestContext:
    requester_id: str
    chat_id: str
    channel: str
    tenant_id: str = "default"


@dataclass(frozen=True)
class BusinessRequest:
    original_query: str
    rewritten_query: str
    intent: str
    business_module: str
    department: str = ""
    period: str = ""
    output_template: str = "default"
    confidence: float = 0.0
    entities: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteResult:
    message: str
    template: str
    payload: dict[str, Any] | None = None
    attachments: tuple[Any, ...] = ()
