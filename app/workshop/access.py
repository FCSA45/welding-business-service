"""Department data boundary shared by workshop entry points and repositories."""

from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass
from typing import Iterable

import httpx

from app.errors import AppError
from app.wecom.client import WeComClient


logger = logging.getLogger(__name__)
NON_PRODUCTION_ENVIRONMENTS = frozenset({"development", "dev", "test", "testing", "local"})


def normalize_department(value: object) -> str:
    """Use the same whitespace policy as query rewriting: remove all whitespace."""
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(normalized.split())


def _normalize_identity(value: object) -> str:
    return "".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _require_identity(requester_id: object, chat_id: object) -> tuple[str, str]:
    requester = _normalize_identity(requester_id)
    chat = _normalize_identity(chat_id)
    if not requester and not chat:
        raise AppError(
            "WORKSHOP_IDENTITY_REQUIRED",
            "缺少用户或会话身份，无法校验部门权限",
            status_code=400,
        )
    return requester, chat


def _clean_departments(
    values: Iterable[object] | object,
    *,
    allow_wildcard: bool,
) -> frozenset[str]:
    if isinstance(values, (str, bytes)) or values is None:
        values = [values]
    try:
        cleaned = {
            normalize_department(item)
            for item in values
            if isinstance(item, str)
        }
    except TypeError:
        cleaned = set()
    cleaned.discard("")
    if not allow_wildcard:
        cleaned.discard("*")
    return frozenset(cleaned)


@dataclass(frozen=True)
class DepartmentScope:
    requester_id: str
    allowed_departments: frozenset[str]

    def require(self, department: str) -> str:
        requested = normalize_department(department)
        if not requested:
            raise AppError("WORKSHOP_DEPARTMENT_REQUIRED", "必须指定业务部门", status_code=400)
        if requested == "*":
            raise AppError(
                "WORKSHOP_DEPARTMENT_INVALID",
                "部门名称无效",
                status_code=400,
            )
        if "*" not in self.allowed_departments and requested not in self.allowed_departments:
            raise AppError("WORKSHOP_DEPARTMENT_FORBIDDEN", "无权读取该部门业务数据", status_code=403)
        return requested


class DepartmentAccessPolicy:
    """Resolve a user/chat identity to an immutable department allow-list."""

    def __init__(self, mapping: str | dict | None, *, environment: str, fallback_department: str) -> None:
        if isinstance(mapping, str):
            try:
                mapping = json.loads(mapping or "{}")
            except json.JSONDecodeError as exc:
                raise AppError(
                    "WORKSHOP_DEPARTMENT_ACCESS_INVALID",
                    "部门权限配置不是有效 JSON",
                    status_code=500,
                ) from exc
        if mapping is not None and not isinstance(mapping, dict):
            raise AppError(
                "WORKSHOP_DEPARTMENT_ACCESS_INVALID",
                "部门权限配置格式无效",
                status_code=500,
            )
        self.mapping = mapping or {}
        self.environment = _normalize_identity(environment).lower()
        self.fallback_department = normalize_department(fallback_department)

    def scope_for(self, requester_id: str, *, chat_id: str = "") -> DepartmentScope:
        requester, chat = _require_identity(requester_id, chat_id)
        raw = self.mapping.get(requester) or self.mapping.get(f"chat:{chat}")
        if raw is None and self.environment in NON_PRODUCTION_ENVIRONMENTS:
            # Development/test compatibility only; production always fails closed.
            raw = self.mapping.get("*") or ["*"]
        allowed = _clean_departments(raw, allow_wildcard=True)
        if not allowed:
            raise AppError(
                "WORKSHOP_DEPARTMENT_ACCESS_DENIED",
                "当前用户未配置车间部门数据权限",
                status_code=403,
            )
        return DepartmentScope(requester_id=requester or chat, allowed_departments=allowed)


def _resolve_live_departments(client: WeComClient, requester_id: str) -> frozenset[str]:
    try:
        departments = client.get_user_departments(requester_id)
    except AppError:
        raise
    except httpx.TimeoutException as exc:
        raise AppError(
            "WECOM_DIRECTORY_TIMEOUT",
            "企业微信部门鉴权超时，请稍后重试",
            status_code=503,
        ) from exc
    except httpx.RequestError as exc:
        raise AppError(
            "WECOM_DIRECTORY_UNAVAILABLE",
            "企业微信部门鉴权服务暂时不可用，请稍后重试",
            status_code=503,
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected WeCom department authorization failure")
        raise AppError(
            "WECOM_DIRECTORY_AUTH_FAILED",
            "企业微信部门鉴权失败，请稍后重试",
            status_code=503,
        ) from exc

    allowed = _clean_departments(departments, allow_wildcard=False)
    if not allowed:
        raise AppError(
            "WECOM_DEPARTMENT_INVALID",
            "企业微信返回的部门信息无效",
            status_code=502,
        )
    return allowed


def resolve_department_scope(settings, requester_id: str, *, chat_id: str = "") -> DepartmentScope:
    """Resolve authorization fresh and fail closed when live auth cannot run."""
    requester, chat = _require_identity(requester_id, chat_id)
    environment = _normalize_identity(getattr(settings, "app_env", "")).lower()
    live_enabled = bool(getattr(settings, "wecom_realtime_department_auth_enabled", True))
    client = WeComClient(settings)
    if live_enabled and client.is_configured:
        if not requester:
            raise AppError(
                "WECOM_REQUESTER_REQUIRED",
                "实时企业微信鉴权需要用户身份",
                status_code=400,
            )
        return DepartmentScope(
            requester_id=requester,
            allowed_departments=_resolve_live_departments(client, requester),
        )
    if live_enabled and environment in {"production", "prod"}:
        raise AppError(
            "WECOM_DIRECTORY_AUTH_REQUIRED",
            "生产环境必须配置企业微信通讯录实时部门鉴权",
            status_code=503,
        )
    return DepartmentAccessPolicy(
        getattr(settings, "workshop_department_access_map", "{}"),
        environment=environment,
        fallback_department=getattr(settings, "workshop_report_department", ""),
    ).scope_for(requester, chat_id=chat)
