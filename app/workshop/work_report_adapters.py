"""Independent adapters for the JianDaoYun workshop work-report form."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.config import Settings
from app.concurrency import run_async_blocking
from app.errors import AppError
from app.integrations.jiandaoyun.client import ReadOnlyJianDaoYunMCPClient
from app.integrations.jiandaoyun.concurrency import run_query
from app.integrations.jiandaoyun.data_api import JianDaoYunDataAPI
from app.workshop.access import DepartmentScope
from app.workshop.card_content import WorkshopWorkReportRecord
from app.workshop.jiandaoyun_mcp import _date_value, _datetime_value, _number, _person_name, _text
from app.workshop.mock_source import load_mock_work_report_records


REQUIRED_FIELD_KEYS = {
    "product_order_no", "report_department", "process_name", "reporter_name",
    "reported_at", "completed_quantity", "completion_rate",
}
WELDING_DEPARTMENT = "焊接部"


def _day_range(report_date: date) -> list[str]:
    """Match the JianDaoYun UI's inclusive full-day datetime filter."""
    value = report_date.isoformat()
    return [f"{value} 00:00:00", f"{value} 23:59:59"]


class WorkshopWorkReportAdapter(Protocol):
    used_snapshot: bool

    def fetch_records(
        self, *, department: str, report_date: date, scope: DepartmentScope | None = None
    ) -> list[WorkshopWorkReportRecord]: ...

    def fetch_detail(
        self, *, department: str, product_order_no: str = "", reporter_name: str = "",
        report_date: date | None = None, scope: DepartmentScope | None = None,
    ) -> list[WorkshopWorkReportRecord]: ...


class MockWorkshopWorkReportAdapter:
    used_snapshot = False

    def __init__(self, path: str) -> None:
        self.path = path

    def fetch_records(
        self, *, department: str, report_date: date, scope: DepartmentScope | None = None
    ) -> list[WorkshopWorkReportRecord]:
        department = scope.require(department) if scope else department.strip()
        timezone = ZoneInfo("Asia/Shanghai")
        return [
            record for record in load_mock_work_report_records(self.path)
            if record.report_department == department
            and record.reported_at.astimezone(timezone).date() == report_date
        ]

    def fetch_detail(
        self, *, department: str, product_order_no: str = "", reporter_name: str = "",
        report_date: date | None = None, scope: DepartmentScope | None = None,
    ) -> list[WorkshopWorkReportRecord]:
        department = scope.require(department) if scope else department.strip()
        rows = load_mock_work_report_records(self.path)
        return [
            record for record in rows
            if record.report_department == department
            and (not product_order_no.strip() or record.product_order_no == product_order_no.strip())
            and (not reporter_name.strip() or record.reporter_name == reporter_name.strip())
            and (report_date is None or record.reported_at.astimezone(ZoneInfo("Asia/Shanghai")).date() == report_date)
        ]


class JianDaoYunWorkReportAdapter:
    used_snapshot = False

    def __init__(
        self,
        settings: Settings,
        client=None,
        *,
        entry_id: str | None = None,
        field_map: str | None = None,
        form_name: str = "车间工序—报工",
        source_prefix: str = "",
    ) -> None:
        self.settings = settings
        self.entry_id = (entry_id or settings.jiandaoyun_work_report_entry_id).strip()
        self.form_name = form_name
        self.source_prefix = source_prefix
        self.fields = self._load_field_map(
            settings.jiandaoyun_work_report_field_map if field_map is None else field_map
        )
        self.client = client or ReadOnlyJianDaoYunMCPClient(
            settings.jiandaoyun_mcp_url,
            timeout_seconds=settings.jiandaoyun_mcp_timeout_seconds,
            retry_max_attempts=settings.jiandaoyun_retry_max_attempts,
        )
        self.data_api = JianDaoYunDataAPI(self.client)

    @property
    def source_forms(self) -> list[dict[str, str]]:
        return [
            {
                "form_name": self.form_name,
                "entry_id": self.entry_id,
                "completed_quantity_field": self.fields["completed_quantity"],
            }
        ]

    @staticmethod
    def _load_field_map(raw: str) -> dict[str, str]:
        try:
            values = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise AppError("WORK_REPORT_FIELD_MAP_INVALID", "报工表字段映射不是有效 JSON", status_code=500) from exc
        if not isinstance(values, dict):
            raise AppError("WORK_REPORT_FIELD_MAP_INVALID", "报工表字段映射必须是 JSON 对象", status_code=500)
        fields = {str(key): str(value).strip() for key, value in values.items() if str(value).strip()}
        missing = sorted(REQUIRED_FIELD_KEYS - fields.keys())
        if missing:
            raise AppError(
                "WORK_REPORT_FIELD_MAP_INCOMPLETE",
                "报工表缺少字段映射：" + "、".join(missing),
                status_code=503,
            )
        return fields

    def fetch_records(
        self, *, department: str, report_date: date, scope: DepartmentScope | None = None
    ) -> list[WorkshopWorkReportRecord]:
        department = scope.require(department) if scope else department.strip()
        if not department:
            raise AppError("WORKSHOP_DEPARTMENT_REQUIRED", "必须指定业务部门", status_code=400)
        query_key = f"{self.source_prefix}work-report|{self.entry_id}|{department}|{report_date.isoformat()}"
        return run_query(
            connection_key=self.settings.jiandaoyun_mcp_url,
            query_key=query_key,
            max_concurrency=self.settings.jiandaoyun_max_concurrency,
            requests_per_second=self.settings.jiandaoyun_requests_per_second,
            singleflight=self.settings.jiandaoyun_singleflight_enabled,
            operation=lambda: run_async_blocking(
                lambda: self._fetch(department, report_date)
            ),
        )

    def fetch_detail(
        self, *, department: str, product_order_no: str = "", reporter_name: str = "",
        report_date: date | None = None, scope: DepartmentScope | None = None,
    ) -> list[WorkshopWorkReportRecord]:
        department = scope.require(department) if scope else department.strip()
        product_order_no = product_order_no.strip()
        reporter_name = reporter_name.strip()
        if not product_order_no and not reporter_name and report_date is None:
            raise AppError("WORK_REPORT_DETAIL_FILTER_REQUIRED", "订单号、报工人员或统计日期至少提供一项", status_code=400)
        query_key = f"{self.source_prefix}work-report-detail|{self.entry_id}|{department}|{product_order_no}|{reporter_name}|{report_date or ''}"
        return run_query(
            connection_key=self.settings.jiandaoyun_mcp_url,
            query_key=query_key,
            max_concurrency=self.settings.jiandaoyun_max_concurrency,
            requests_per_second=self.settings.jiandaoyun_requests_per_second,
            singleflight=self.settings.jiandaoyun_singleflight_enabled,
            operation=lambda: run_async_blocking(
                lambda: self._fetch_detail(department, product_order_no, reporter_name, report_date)
            ),
        )

    async def _fetch(self, department: str, report_date: date) -> list[WorkshopWorkReportRecord]:
        rows = await self.data_api.list_records(
            app_id=self.settings.jiandaoyun_workshop_app_id,
            entry_id=self.entry_id,
            fields=[*set(self.fields.values()), "createTime", "updateTime"],
            conditions=[
                {"field": self.fields["report_department"], "type": "text", "method": "eq", "value": [department]},
                {"field": self.fields["reported_at"], "type": "datetime", "method": "range", "value": _day_range(report_date)},
            ],
        )
        records = [self._map_row(row, report_date) for row in rows]
        timezone = ZoneInfo(self.settings.app_timezone)
        return [row for row in records if row.reported_at.astimezone(timezone).date() == report_date]

    async def _fetch_detail(
        self, department: str, product_order_no: str, reporter_name: str, report_date: date | None,
    ) -> list[WorkshopWorkReportRecord]:
        conditions = [
            {"field": self.fields["report_department"], "type": "text", "method": "eq", "value": [department]},
        ]
        if product_order_no:
            conditions.append({"field": self.fields["product_order_no"], "type": "text", "method": "eq", "value": [product_order_no]})
        if reporter_name:
            conditions.append({"field": self.fields["reporter_name"], "type": "text", "method": "eq", "value": [reporter_name]})
        if report_date:
            conditions.append({"field": self.fields["reported_at"], "type": "datetime", "method": "range", "value": _day_range(report_date)})
        rows = await self.data_api.list_records(
            app_id=self.settings.jiandaoyun_workshop_app_id,
            entry_id=self.entry_id,
            fields=[*set(self.fields.values()), "createTime", "updateTime"],
            conditions=conditions,
        )
        mapped = [self._map_row(row, report_date or datetime.now(ZoneInfo(self.settings.app_timezone)).date()) for row in rows]
        if report_date:
            timezone = ZoneInfo(self.settings.app_timezone)
            mapped = [row for row in mapped if row.reported_at.astimezone(timezone).date() == report_date]
        return mapped

    def _value(self, row: dict, key: str):
        field_id = self.fields.get(key)
        return row.get(field_id) if field_id else None

    def _map_row(self, row: dict, report_date: date) -> WorkshopWorkReportRecord:
        timezone = ZoneInfo(self.settings.app_timezone)
        reported_at = _datetime_value(self._value(row, "reported_at"), timezone)
        if reported_at is None:
            raise AppError("WORK_REPORT_RECORD_INVALID", "报工记录缺少报工时间", status_code=502)
        submitted_at = _datetime_value(row.get("createTime"), timezone) or reported_at
        updated_at = _datetime_value(row.get("updateTime"), timezone) or submitted_at
        completed_value = self._value(row, "completed_quantity")
        if completed_value is None or str(completed_value).strip() == "":
            raise AppError(
                "WORK_REPORT_COMPLETED_QUANTITY_MISSING",
                f"{self.form_name}记录缺少总公分数字段，已拒绝估算",
                status_code=502,
                details={"source_record_id": str(row.get("_id") or "")},
            )
        completed = max(0.0, _number(completed_value))
        planned_value = self._value(row, "planned_quantity")
        planned = max(completed, _number(planned_value)) if planned_value is not None else completed
        raw_rate = _number(self._value(row, "completion_rate"))
        raw_rate = raw_rate / 100 if raw_rate > 1 else raw_rate
        rate = max(0.0, min(1.0, raw_rate))
        order_date = _date_value(self._value(row, "order_date")) or report_date
        delivery_date = _date_value(self._value(row, "delivery_date")) or report_date
        if delivery_date < order_date:
            order_date = delivery_date
        unit = _text(self._value(row, "quantity_unit")) or "公分"
        if unit not in {"米", "公分", "件"}:
            raise AppError("WORK_REPORT_UNIT_INVALID", f"无法识别报工单位：{unit or '空'}", status_code=502)
        return WorkshopWorkReportRecord(
            source_record_id=f"{self.source_prefix}{str(row.get('_id') or '').strip()}",
            source_form_name=self.form_name,
            product_order_no=_text(self._value(row, "product_order_no")),
            salesperson=_person_name(self._value(row, "salesperson")),
            workshop=_text(self._value(row, "workshop")) or "车间",
            order_date=order_date,
            delivery_date=delivery_date,
            product_name=_text(self._value(row, "product_name")) or "未填写产品",
            product_quantity=max(0, int(_number(self._value(row, "product_quantity")))),
            planned_quantity=planned,
            completed_quantity=completed,
            quantity_unit=unit,
            color=_text(self._value(row, "color")),
            process_name=_text(self._value(row, "process_name")),
            process_status=_text(self._value(row, "process_status")) or "已报工",
            scheduled_at=_datetime_value(self._value(row, "scheduled_at"), timezone),
            report_department=_text(self._value(row, "report_department")),
            reportable_process=_text(self._value(row, "reportable_process")),
            reporter_name=_person_name(self._value(row, "reporter_name")) or _text(self._value(row, "reporter_name")),
            reported_at=reported_at,
            completion_rate=round(rate, 6),
            remark=_text(self._value(row, "remark")),
            submitted_at=min(submitted_at, updated_at),
            updated_at=max(submitted_at, updated_at),
        )


class CombinedWorkshopWorkReportAdapter:
    """Use the standard report form and add the pick-order form for welding."""

    used_snapshot = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.primary = JianDaoYunWorkReportAdapter(settings)
        pick_entry_id = settings.jiandaoyun_welding_pick_work_report_entry_id.strip()
        pick_field_map = settings.jiandaoyun_welding_pick_work_report_field_map
        if not pick_entry_id:
            raise AppError(
                "WELDING_PICK_WORK_REPORT_CONFIG_MISSING",
                "焊接部缺少抽单工序—报工表配置",
                status_code=503,
            )
        self.welding_pick = JianDaoYunWorkReportAdapter(
            settings,
            entry_id=pick_entry_id,
            field_map=pick_field_map,
            form_name="抽单工序—报工",
            source_prefix="pick:",
        )
        self.fields = self.primary.fields

    def _adapters_for(self, department: str) -> tuple[JianDaoYunWorkReportAdapter, ...]:
        return (
            (self.primary, self.welding_pick)
            if department == WELDING_DEPARTMENT
            else (self.primary,)
        )

    def source_forms_for(self, department: str) -> list[dict[str, str]]:
        return [
            source
            for adapter in self._adapters_for(department)
            for source in adapter.source_forms
        ]

    def fetch_records(
        self, *, department: str, report_date: date, scope: DepartmentScope | None = None
    ) -> list[WorkshopWorkReportRecord]:
        department = scope.require(department) if scope else department.strip()
        adapters = self._adapters_for(department)
        if len(adapters) == 1:
            return adapters[0].fetch_records(
                department=department, report_date=report_date, scope=None
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    adapter.fetch_records,
                    department=department,
                    report_date=report_date,
                    scope=None,
                )
                for adapter in adapters
            ]
            return [row for future in futures for row in future.result()]

    def fetch_detail(
        self,
        *,
        department: str,
        product_order_no: str = "",
        reporter_name: str = "",
        report_date: date | None = None,
        scope: DepartmentScope | None = None,
    ) -> list[WorkshopWorkReportRecord]:
        department = scope.require(department) if scope else department.strip()
        adapters = self._adapters_for(department)
        if len(adapters) == 1:
            return adapters[0].fetch_detail(
                department=department,
                product_order_no=product_order_no,
                reporter_name=reporter_name,
                report_date=report_date,
                scope=None,
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    adapter.fetch_detail,
                    department=department,
                    product_order_no=product_order_no,
                    reporter_name=reporter_name,
                    report_date=report_date,
                    scope=None,
                )
                for adapter in adapters
            ]
            return [row for future in futures for row in future.result()]


def build_work_report_adapter(settings: Settings) -> WorkshopWorkReportAdapter:
    adapter = settings.workshop_work_report_adapter
    if adapter == "mock":
        if settings.app_env.lower() in {"production", "prod"} and not settings.workshop_allow_mock_in_production:
            raise AppError("WORK_REPORT_MOCK_FORBIDDEN", "生产环境禁止使用报工模拟数据", status_code=503)
        return MockWorkshopWorkReportAdapter(settings.workshop_work_report_mock_data_path)
    if adapter == "jiandaoyun_mcp":
        return CombinedWorkshopWorkReportAdapter(settings)
    raise AppError("WORK_REPORT_ADAPTER_INVALID", "未知的报工数据适配器", status_code=503)
