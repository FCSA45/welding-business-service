"""Database-free scheduled department report generation and delivery."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.config import Settings, get_settings
from app.errors import AppError
from app.wecom.bot_bindings import WeComBotBinding, build_wecom_bot_bindings
from app.wecom.long_connection import WeComAIBotRunner
from app.workshop.access import DepartmentScope
from app.workshop.adapters import build_workshop_adapter
from app.workshop.department_report_service import DepartmentOrderReportService
from app.workshop.outputs.wecom_markdown import render_department_report_markdown
from app.workshop.work_report_handler import render_work_report_markdown
from app.workshop.work_report_service import WorkReportService
from app.workshop.wecom_report_artifacts import (
    build_order_report_png,
    build_work_report_png,
)


logger = logging.getLogger("scheduled_reports")


@dataclass(frozen=True)
class ScheduledAttachment:
    kind: str
    message: str
    png_path: Path
    html_path: Path | None = None


def _parse_targets(settings: Settings) -> dict[str, tuple[str, ...]]:
    raw = str(settings.workshop_scheduled_report_targets or "{}").strip()
    try:
        values = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(
            "SCHEDULED_REPORT_TARGETS_INVALID",
            "定时报告目标群配置不是有效 JSON。",
            status_code=500,
        ) from exc
    if not isinstance(values, dict):
        raise AppError("SCHEDULED_REPORT_TARGETS_INVALID", "定时报告目标群配置格式无效。", status_code=500)
    targets: dict[str, tuple[str, ...]] = {}
    for key, item in values.items():
        if isinstance(item, str):
            item = [item]
        if not isinstance(item, list):
            raise AppError("SCHEDULED_REPORT_TARGETS_INVALID", f"部门机器人 {key} 的目标群配置无效。", status_code=500)
        cleaned = tuple(dict.fromkeys(str(value).strip() for value in item if str(value).strip()))
        if cleaned:
            targets[str(key).strip()] = cleaned
    if not targets:
        raise AppError("SCHEDULED_REPORT_TARGETS_EMPTY", "没有配置定时报告目标群。", status_code=500)
    return targets


def _report_date(settings: Settings, requested: str | None) -> date:
    if requested:
        try:
            return date.fromisoformat(requested)
        except ValueError as exc:
            raise AppError("SCHEDULED_REPORT_DATE_INVALID", "定时报告日期必须是 YYYY-MM-DD。", status_code=400) from exc
    return datetime.now(ZoneInfo(settings.app_timezone)).date() - timedelta(days=1)


def _scope(binding: WeComBotBinding) -> DepartmentScope:
    return DepartmentScope(
        requester_id=f"scheduled:{binding.key}",
        allowed_departments=frozenset({binding.department}),
    )


def _source_label(settings: Settings) -> str:
    if settings.workshop_data_adapter == "mock":
        return "模拟数据"
    return "简道云正式数据"


def _build_reports(
    settings: Settings,
    binding: WeComBotBinding,
    report_date: date,
) -> list[ScheduledAttachment]:
    scope = _scope(binding)
    attachments: list[ScheduledAttachment] = []
    request_id = uuid4().hex

    if settings.workshop_scheduled_report_include_order:
        order_adapter = build_workshop_adapter(settings)
        order_payload = DepartmentOrderReportService(order_adapter).generate(
            department=binding.department,
            statistics_date=report_date,
            timezone=settings.app_timezone,
            scope=scope,
        )
        source_label = _source_label(settings)
        if getattr(order_adapter, "used_snapshot", False):
            source_label += "（最近成功快照）"
        message = render_department_report_markdown(order_payload, source_label=source_label)
        html_path, png_path = build_order_report_png(
            order_payload,
            settings,
            request_id=request_id,
        )
        attachments.append(ScheduledAttachment("order_daily", message, png_path, html_path))

    if settings.workshop_scheduled_report_include_work:
        work_result = WorkReportService(settings).build_daily_report(
            department=binding.department,
            report_date=report_date,
            scope=scope,
        )
        message = render_work_report_markdown(
            work_result.payload,
            source_label=work_result.source_label,
        )
        html_path, png_path = build_work_report_png(
            work_result.payload,
            settings,
            request_id=request_id,
        )
        attachments.append(ScheduledAttachment("work_daily", message, png_path, html_path))

    if not attachments:
        raise AppError(
            "SCHEDULED_REPORT_EMPTY",
            "日报和报工日报均未启用，无法执行定时发送。",
            status_code=500,
        )
    return attachments


def _safe_marker_name(binding_key: str, target_id: str, report_date: date) -> str:
    safe_target = re.sub(r"[^A-Za-z0-9_.-]", "_", target_id)[:80] or "target"
    return f"{report_date.isoformat()}-{binding_key}-{safe_target}.json"


def _marker_path(settings: Settings, binding_key: str, target_id: str, report_date: date) -> Path:
    return Path(settings.workshop_scheduled_report_state_dir).resolve() / _safe_marker_name(
        binding_key, target_id, report_date
    )


async def _deliver_binding(
    settings: Settings,
    binding: WeComBotBinding,
    target_ids: tuple[str, ...],
    attachments: list[ScheduledAttachment],
    report_date: date,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    state: dict[str, Any] = {"binding": binding.key, "department": binding.department, "sent": [], "skipped": []}
    pending: list[tuple[str, list[ScheduledAttachment]]] = []
    for target_id in target_ids:
        marker = _marker_path(settings, binding.key, target_id, report_date)
        if marker.is_file():
            state["skipped"].append(target_id)
        else:
            pending.append((target_id, attachments))
    if dry_run or not pending:
        state["dry_run"] = dry_run
        state["pending"] = [target for target, _ in pending]
        return state

    runner = WeComAIBotRunner(settings, binding=binding)
    await runner.connect_for_delivery()
    try:
        for target_id, target_attachments in pending:
            for attachment in target_attachments:
                await runner.send_text(target_id, attachment.message)
                await runner.send_media(target_id, str(attachment.png_path))
            marker = _marker_path(settings, binding.key, target_id, report_date)
            marker.parent.mkdir(parents=True, exist_ok=True)
            temporary = marker.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "binding": binding.key,
                        "department": binding.department,
                        "target_id": target_id,
                        "report_date": report_date.isoformat(),
                        "sent_at": datetime.now(ZoneInfo(settings.app_timezone)).isoformat(),
                        "attachments": [item.kind for item in target_attachments],
                        "png_paths": [str(item.png_path) for item in target_attachments],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(marker)
            state["sent"].append(target_id)
    finally:
        await runner.close_after_delivery()
    return state


async def run_scheduled_reports(
    settings: Settings | None = None,
    *,
    requested_date: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.workshop_scheduled_report_enabled:
        return {"status": "disabled", "sent": []}
    report_date = _report_date(settings, requested_date)
    targets = _parse_targets(settings)
    bindings = {binding.key: binding for binding in build_wecom_bot_bindings(settings)}
    result: dict[str, Any] = {"status": "ok", "report_date": report_date.isoformat(), "bindings": []}
    for binding_key, target_ids in targets.items():
        binding = bindings.get(binding_key)
        if binding is None:
            raise AppError("SCHEDULED_REPORT_BINDING_INVALID", f"未找到机器人绑定：{binding_key}。", status_code=500)
        if not binding.enabled:
            raise AppError("SCHEDULED_REPORT_BINDING_DISABLED", f"机器人未启用：{binding_key}。", status_code=503)
        if not binding.configured:
            raise AppError("SCHEDULED_REPORT_BINDING_UNCONFIGURED", f"机器人未配置凭据：{binding_key}。", status_code=503)
        attachments = await asyncio.to_thread(_build_reports, settings, binding, report_date)
        result["bindings"].append(
            await _deliver_binding(
                settings,
                binding,
                target_ids,
                attachments,
                report_date,
                dry_run=dry_run,
            )
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Send scheduled department order and work reports.")
    parser.add_argument("--date", dest="report_date", help="Override report date as YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Generate artifacts but do not send messages")
    args = parser.parse_args()
    logging.basicConfig(level="INFO")
    result = asyncio.run(
        run_scheduled_reports(requested_date=args.report_date, dry_run=args.dry_run)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
