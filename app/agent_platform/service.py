import os
import re
from datetime import date

from app.agent_platform.repository import KnowledgeRepository, PermissionRepository
from app.agent_platform.search import KnowledgeHit, KnowledgeSearchService, normalize_text
from app.config import Settings
from app.errors import AppError


def _normalize(value: str) -> str:
    return normalize_text(value)


class PermissionService:
    def __init__(self, repository: PermissionRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def ensure_agent_access(self, subject_id: str | None, agent_id: str) -> None:
        if self.settings.platform_permission_mode.lower() == "open":
            return
        if not subject_id or self.repository.find(subject_id, agent_id) is None:
            raise AppError("AGENT_ACCESS_DENIED", "你没有使用该智能体的权限", status_code=403)


def data_source_readiness(
    *,
    adapter_type: str,
    settings_json: dict,
    secret_env_key: str,
    enabled: bool,
) -> tuple[bool, str]:
    if not enabled:
        return False, "尚未启用"
    if adapter_type == "manual":
        return True, "可手动录入数据"
    if adapter_type == "csv":
        path = str(settings_json.get("path") or "").strip()
        return (bool(path), "CSV 路径已配置" if path else "缺少 CSV 路径")
    if adapter_type == "http_api":
        base_url = str(settings_json.get("base_url") or "").strip()
        if not base_url:
            return False, "缺少 API 地址"
        if secret_env_key and not os.getenv(secret_env_key):
            return False, f"缺少环境变量 {secret_env_key}"
        return True, "API 基础配置已就绪"
    if adapter_type == "database":
        if not secret_env_key:
            return False, "缺少数据库连接环境变量名称"
        return (
            bool(os.getenv(secret_env_key)),
            "数据库连接配置已就绪" if os.getenv(secret_env_key) else f"缺少环境变量 {secret_env_key}",
        )
    if adapter_type == "webhook":
        return True, "Webhook 入口可配置"
    return False, "不支持的数据源类型"


def report_period_from_message(message: str) -> str | None:
    normalized = _normalize(message)
    if "月报" in normalized or "本月" in normalized:
        return "monthly"
    if "周报" in normalized or "本周" in normalized:
        return "weekly"
    if "日报" in normalized or "今天" in normalized or "今日" in normalized:
        return "daily"
    return None


def report_range(period: str, anchor_date: date) -> tuple[date, date]:
    from app.reports.models import ReportPeriod
    from app.reports.periods import resolve_period

    return resolve_period(ReportPeriod(period), anchor_date)
