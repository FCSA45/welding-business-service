"""Generate a department work-report daily report from workshop process rows."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.business_routing.models import BusinessRequest, RequestContext, RouteResult
from app.config import Settings
from app.workshop.access import resolve_department_scope
from app.workshop.work_report_service import WorkReportService


def render_work_report_markdown(payload: dict, *, source_label: str) -> str:
    rate = float(payload.get("report_rate", 0) or 0)
    completed_pieces = float(payload.get("completed_pieces", 0) or 0)
    completed_piece_text = f"｜完成 **{completed_pieces:.0f} 件**" if completed_pieces else ""
    performer_lines = []
    for index, row in enumerate(payload.get("top_performers", []), start=1):
        amount = f"{float(row['completed_centimeters']):.2f} 公分"
        if row.get("completed_pieces"):
            amount += f" / {float(row['completed_pieces']):.0f} 件"
        performer_lines.append(
            f"{index}. **{row['reporter_name']}**｜完成 {amount}｜"
            f"平均完成率 {float(row['completion_rate']):.1%}｜报工 {row['report_count']} 条"
        )
    source_lines = [
        f"- {row['form_name']}：{row['raw_record_count']} - "
        f"{row['excluded_quality_inspection_record_count']} = {row['included_record_count']} 条"
        for row in payload.get("source_record_breakdown", [])
    ]
    return (
        f"# {payload['department']}｜车间报工日报\n"
        f"> 报告日期：**{payload['report_date']}**｜数据源：{source_label}\n\n"
        f"## 报工概览\n"
        f"状态：**{payload['health_status']}**｜{payload['health_summary']}\n"
        f"简道云筛选报工记录 **{payload['report_record_count']}**｜去重后参与统计 **{payload['deduplicated_report_record_count']}**｜"
        f"应报工订单工序 **{payload['expected_count']}**｜"
        f"报工表实际订单工序 **{payload['reported_count']}**｜匹配计划工序 **{payload['matched_reported_count']}**｜"
        f"未报工订单工序 **{payload['pending_report_count']}**｜"
        f"报工率 **{rate:.1%}**\n"
        f"完成订单数 **{payload['completed_order_count']}**｜完成 **{payload['completed_centimeters']:.2f} 公分**"
        f"{completed_piece_text}\n\n"
        f"## 报工记录口径\n"
        f"{chr(10).join(source_lines) or '- 暂无报工来源明细'}\n"
        f"- 合计：{payload.get('report_record_count_before_exclusions', 0)} - "
        f"{payload.get('excluded_quality_inspection_record_count', 0)} = "
        f"**{payload['report_record_count']} 条有效报工记录**\n\n"
        f"## 人员报工表现（前 {len(performer_lines)} 名）\n"
        f"{chr(10).join(performer_lines) or '- 当日暂无有效报工人员数据'}\n\n"
        f"## 待处理\n"
        f"- 未报工订单工序：**{payload['pending_report_count']}**\n"
        f"- 无法匹配计划工序的报工记录：**{payload['unmatched_report_record_count']} 条**，涉及工序 **{payload['unmatched_report_count']} 个**\n"
        f"- 排除质检工序：**{payload.get('excluded_quality_inspection_record_count', 0)} 条**\n\n"
        "> 工序名称包含“质检”的记录不计入部门报工统计。\n"
        "> 长度只读取各报工表的“总公分数/总米数”字段，统一按公分展示；完成订单数按产品订单号去重。"
    )


class WorkshopWorkReportHandler:
    def __init__(self, settings: Settings, service: WorkReportService | None = None) -> None:
        self.settings = settings
        self.service = service

    def handle(self, request: BusinessRequest, context: RequestContext) -> RouteResult:
        scope = resolve_department_scope(
            self.settings, context.requester_id, chat_id=context.chat_id
        )
        department = scope.require(request.department or self.settings.workshop_report_department)
        current_date = datetime.now(ZoneInfo(self.settings.app_timezone)).date()
        explicit_statistics_date = str(request.entities.get("statistics_date", "") or "").strip()
        if explicit_statistics_date:
            try:
                report_date = date.fromisoformat(explicit_statistics_date)
            except ValueError as exc:
                raise ValueError("statistics_date must use YYYY-MM-DD") from exc
        else:
            anchor_days_ago = int(request.entities.get("anchor_days_ago", "1"))
            report_date = current_date - timedelta(days=anchor_days_ago)
        result = (self.service or WorkReportService(self.settings)).build_daily_report(
            department=department,
            report_date=report_date,
            scope=scope,
        )
        payload = result.payload
        message = render_work_report_markdown(payload, source_label=result.source_label)
        return RouteResult(
            message=message,
            template="wecom_work_report",
            payload=payload,
        )
