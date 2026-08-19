"""Validate the production, database-free MCP runtime configuration."""

from __future__ import annotations

import json
import sys

from app.config import get_settings
from app.wecom.bot_bindings import build_wecom_bot_bindings


def main() -> int:
    settings = get_settings()
    errors: list[str] = []

    if settings.app_env.lower() not in {"production", "prod"}:
        errors.append("APP_ENV must be production for a cloud deployment")
    if settings.model_enabled:
        errors.append("MODEL_ENABLED must be false; Cherry/Hermes owns model calls")
    if settings.mcp_knowledge_tools_enabled:
        errors.append(
            "MCP_KNOWLEDGE_TOOLS_ENABLED must be false for the database-free profile"
        )
    if settings.workshop_data_adapter != "jiandaoyun_mcp":
        errors.append("WORKSHOP_DATA_ADAPTER must be jiandaoyun_mcp")
    if settings.workshop_work_report_adapter != "jiandaoyun_mcp":
        errors.append("WORKSHOP_WORK_REPORT_ADAPTER must be jiandaoyun_mcp")
    if not settings.jiandaoyun_mcp_url:
        errors.append("JIANDAOYUN_MCP_URL is required")
    if not settings.jiandaoyun_workshop_app_id:
        errors.append("JIANDAOYUN_WORKSHOP_APP_ID is required")
    if not settings.jiandaoyun_workshop_entry_id:
        errors.append("JIANDAOYUN_WORKSHOP_ENTRY_ID is required")
    if not settings.jiandaoyun_work_report_entry_id:
        errors.append("JIANDAOYUN_WORK_REPORT_ENTRY_ID is required")
    if not settings.jiandaoyun_welding_pick_work_report_entry_id:
        errors.append("JIANDAOYUN_WELDING_PICK_WORK_REPORT_ENTRY_ID is required for welding reports")
    if settings.wecom_realtime_department_auth_enabled:
        for name, value in (
            ("WECOM_CORP_ID", settings.wecom_corp_id),
            ("WECOM_CORP_SECRET", settings.wecom_corp_secret),
        ):
            if not value:
                errors.append(f"{name} is required when live WeCom authorization is enabled")
    if settings.workshop_department_access_map not in ({}, "{}"):
        try:
            mapping = settings.workshop_department_access_map
            if isinstance(mapping, str):
                mapping = json.loads(mapping)
            if mapping:
                errors.append("WORKSHOP_DEPARTMENT_ACCESS_MAP must be empty in production")
        except (TypeError, ValueError):
            errors.append("WORKSHOP_DEPARTMENT_ACCESS_MAP must be valid JSON")

    if settings.workshop_scheduled_report_enabled:
        try:
            targets = json.loads(settings.workshop_scheduled_report_targets or "{}")
        except json.JSONDecodeError:
            targets = None
            errors.append("WORKSHOP_SCHEDULED_REPORT_TARGETS must be valid JSON")
        if not isinstance(targets, dict) or not targets:
            errors.append("WORKSHOP_SCHEDULED_REPORT_TARGETS must contain at least one bot-to-chat mapping")
        else:
            bindings = {binding.key: binding for binding in build_wecom_bot_bindings(settings)}
            for key, value in targets.items():
                target_ids = [value] if isinstance(value, str) else value
                if not isinstance(target_ids, list) or not target_ids:
                    errors.append(f"scheduled report target for {key} must be a non-empty chat ID list")
                    continue
                if any(
                    not isinstance(chat_id, str)
                    or not chat_id.strip()
                    or "replace-with" in chat_id.lower()
                    for chat_id in target_ids
                ):
                    errors.append(f"scheduled report target for {key} contains a placeholder or empty chat ID")
                binding = bindings.get(str(key))
                if binding is None:
                    errors.append(f"scheduled report bot binding does not exist: {key}")
                elif not binding.enabled:
                    errors.append(f"scheduled report bot must be enabled: {key}")
                elif not binding.configured:
                    errors.append(f"scheduled report bot credentials are missing: {key}")

    if errors:
        print("MCP configuration is NOT ready:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("MCP configuration is ready: production, JianDaoYun MCP, live WeCom authorization, no database")
    return 0


if __name__ == "__main__":
    sys.exit(main())
