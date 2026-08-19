"""Reusable, department-neutral work-report application service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.config import Settings
from app.workshop.access import DepartmentScope
from app.workshop.adapters import build_workshop_adapter
from app.workshop.card_content import build_work_report_summary
from app.workshop.work_report_adapters import build_work_report_adapter


@dataclass(frozen=True)
class WorkReportResult:
    payload: dict
    source_label: str


class WorkReportService:
    """Build a work-report daily summary for any authorized department.

    Channel handlers only resolve the caller and requested date. Data retrieval,
    cross-chain joining and aggregation live here so HTTP, scheduled jobs and
    other departments can reuse the same business path.
    """

    def __init__(self, settings: Settings, *, order_adapter=None, report_adapter=None) -> None:
        self.settings = settings
        self.order_adapter = order_adapter or build_workshop_adapter(settings)
        self.report_adapter = report_adapter or build_work_report_adapter(settings)

    def build_daily_report(
        self,
        *,
        department: str,
        report_date: date,
        scope: DepartmentScope,
    ) -> WorkReportResult:
        department = scope.require(department)
        plans = self.order_adapter.fetch_plan_records(
            department=department,
            start_date=report_date,
            end_date=report_date,
            scope=scope,
        )
        reports = self.report_adapter.fetch_records(
            department=department,
            report_date=report_date,
            scope=scope,
        )
        payload = build_work_report_summary(
            plans,
            reports,
            department=department,
            report_date=report_date,
            timezone=self.settings.app_timezone,
            top_limit=self.settings.workshop_card_item_limit,
        )
        payload["data_source"] = {
            "form_name": "车间工序—报工",
            "app_id": self.settings.jiandaoyun_workshop_app_id,
            "entry_id": self.settings.jiandaoyun_work_report_entry_id,
            "completed_quantity_field": getattr(self.report_adapter, "fields", {}).get(
                "completed_quantity", "mock.completed_quantity"
            ),
            "quantity_unit": "公分",
            "strict_source_only": self.settings.workshop_work_report_adapter == "jiandaoyun_mcp",
        }
        if hasattr(self.report_adapter, "source_forms_for"):
            source_forms = self.report_adapter.source_forms_for(department)
            payload["data_source"]["forms"] = source_forms
            breakdown = {
                row["form_name"]: row
                for row in payload.get("source_record_breakdown", [])
            }
            payload["source_record_breakdown"] = [
                breakdown.get(
                    source["form_name"],
                    {
                        "form_name": source["form_name"],
                        "raw_record_count": 0,
                        "excluded_quality_inspection_record_count": 0,
                        "included_record_count": 0,
                    },
                )
                for source in source_forms
            ]
        payload["data_source"]["excluded_process_rule"] = "工序名称包含‘质检’的记录不计入部门报工统计"
        payload["data_source"]["quantity_rule"] = "只读取各报工表的总公分数/总米数映射字段，统一按公分展示"
        payload["data_source"]["completed_order_rule"] = "distinct(产品订单号)"
        payload["empty"] = payload["expected_count"] == 0 and payload["reported_count"] == 0

        order_source = "模拟订单" if self.settings.workshop_data_adapter == "mock" else "简道云订单"
        if self.settings.workshop_work_report_adapter == "mock":
            report_source = "模拟报工"
        elif department == "焊接部":
            report_source = "简道云报工（车间工序—报工 + 抽单工序—报工）"
        else:
            report_source = "简道云报工（车间工序—报工）"
        source_label = f"{order_source} + {report_source}"
        if getattr(self.order_adapter, "used_snapshot", False) or getattr(
            self.report_adapter, "used_snapshot", False
        ):
            source_label += "（最近成功快照）"
        return WorkReportResult(payload=payload, source_label=source_label)
