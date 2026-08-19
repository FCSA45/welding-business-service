"""Application handler for an authorized department report request."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.business_routing.models import BusinessRequest, RequestContext, RouteResult
from app.config import Settings
from app.errors import AppError
from app.workshop.access import resolve_department_scope
from app.workshop.adapters import build_workshop_adapter
from app.workshop.department_report_service import DepartmentOrderReportService
from app.workshop.outputs.registry import OutputTemplateRegistry
from app.workshop.outputs.wecom_markdown import render_department_report_markdown


logger = logging.getLogger(__name__)


DEFAULT_TEMPLATE = "wecom_department_report"
MIN_ANCHOR_DAYS_AGO = 0
MAX_ANCHOR_DAYS_AGO = 366


def _parse_anchor_days_ago(request: BusinessRequest) -> int:
    raw_value = request.entities.get("anchor_days_ago", "0")
    try:
        anchor_days_ago = int(raw_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AppError(
            "WORKSHOP_ANCHOR_INVALID",
            "报告日期参数无效，请使用合法的日期或时间范围。",
            status_code=400,
        ) from exc
    if not MIN_ANCHOR_DAYS_AGO <= anchor_days_ago <= MAX_ANCHOR_DAYS_AGO:
        raise AppError(
            "WORKSHOP_ANCHOR_OUT_OF_RANGE",
            "报告日期超出可查询范围，请查询最近一年内的数据。",
            status_code=400,
        )
    return anchor_days_ago


def _resolve_statistics_date(
    request: BusinessRequest,
    *,
    current_date: date,
) -> date:
    explicit_statistics_date = str(request.entities.get("statistics_date", "") or "").strip()
    if explicit_statistics_date:
        try:
            return date.fromisoformat(explicit_statistics_date)
        except (TypeError, ValueError) as exc:
            raise AppError(
                "WORKSHOP_REPORT_DATE_INVALID",
                "报告日期格式无效，请使用 YYYY-MM-DD 格式。",
                status_code=400,
            ) from exc
    return current_date - timedelta(days=_parse_anchor_days_ago(request))


def _error_result(request: BusinessRequest, message: str, code: str) -> RouteResult:
    template = getattr(request, "output_template", "") or DEFAULT_TEMPLATE
    return RouteResult(
        message=f"⚠️ {message}",
        template=template,
        payload={"ok": False, "error_code": code, "error": message},
    )


class WorkshopDailyReportHandler:
    def __init__(
        self,
        settings: Settings,
        *,
        output_templates: OutputTemplateRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.outputs = output_templates or OutputTemplateRegistry()
        if not self.outputs.contains(DEFAULT_TEMPLATE):
            self.outputs.register(DEFAULT_TEMPLATE, render_department_report_markdown)

    def handle(self, request: BusinessRequest, context: RequestContext) -> RouteResult:
        """Build a report result; application errors are never exposed to callers."""
        try:
            scope = resolve_department_scope(
                self.settings, context.requester_id, chat_id=context.chat_id
            )
            department = scope.require(
                request.department or self.settings.workshop_report_department
            )
            adapter = build_workshop_adapter(self.settings)
            current_date = datetime.now(ZoneInfo(self.settings.app_timezone)).date()
            statistics_date = _resolve_statistics_date(request, current_date=current_date)
            logger.info(
                "Workshop order report date resolved channel=%s department=%s "
                "statistics_date=%s requested_statistics_date=%s anchor_days_ago=%s",
                context.channel,
                department,
                statistics_date.isoformat(),
                request.entities.get("statistics_date", ""),
                request.entities.get("anchor_days_ago", ""),
            )
            payload = DepartmentOrderReportService(adapter).generate(
                department=department,
                statistics_date=statistics_date,
                timezone=self.settings.app_timezone,
                scope=scope,
            )
            source_label = "模拟数据" if self.settings.workshop_data_adapter == "mock" else "正式数据"
            if getattr(adapter, "used_snapshot", False):
                source_label += "（当日最近成功快照）"
            template_name = request.output_template or DEFAULT_TEMPLATE
            message = self.outputs.render(template_name, payload, source_label=source_label)
            return RouteResult(message=message, template=template_name, payload=payload)
        except AppError as exc:
            logger.warning(
                "Workshop daily report rejected code=%s requester_id=%s",
                exc.code,
                getattr(context, "requester_id", ""),
            )
            return _error_result(request, exc.message, exc.code)
        except Exception as exc:
            logger.exception(
                "Workshop daily report failed requester_id=%s",
                getattr(context, "requester_id", ""),
            )
            return _error_result(
                request,
                "报告生成失败，请稍后重试；如果持续失败，请联系管理员。",
                "WORKSHOP_REPORT_FAILED",
            )
