"""Read-only JianDaoYun MCP adapter for workshop process records."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.config import Settings
from app.concurrency import run_async_blocking
from app.errors import AppError
from app.integrations.jiandaoyun.client import (
    DEFAULT_READ_ONLY_TOOLS as READ_ONLY_TOOLS,
    ReadOnlyJianDaoYunMCPClient,
)
from app.integrations.jiandaoyun.data_api import JianDaoYunDataAPI
from app.integrations.jiandaoyun.concurrency import run_query
from app.workshop.access import DepartmentScope
from app.workshop.models import WorkshopProcessRecord


FIELDS = {
    "order_code": "_widget_1747985814740",
    "product_order_no": "_widget_1711765404135",
    "picking_no": "_widget_1732763912579",
    "salesperson": "_widget_1724234374976",
    "workshop": "_widget_1747983789418",
    "order_date": "_widget_1724234374977",
    "delivery_date": "_widget_1724234374978",
    "product_name": "_widget_1711768805334",
    "product_quantity": "_widget_1733888194049",
    "measure": "_widget_1733888283368",
    "color": "_widget_1748062711895",
    "department": "_widget_1722564127159",
    "process_name": "_widget_1722564127161",
    "process_status": "_widget_1722564127163",
    "reporter_name": "_widget_1747983789471",
    "reported_at": "_widget_1736220388919",
    "completion_rate": "_widget_1747983789419",
    "owner": "_widget_1734610685199",
    "remark": "_widget_1722847572334",
    "customer_grade": "_widget_1777513536430",
    "planned_completion_at": "_widget_1748255431630",
}

_RECORD_CACHE: dict[tuple[str, str, date, str], list[WorkshopProcessRecord]] = {}
_CACHE_LOCK = threading.Lock()


def _day_range(value: date) -> list[str]:
    """Match the JianDaoYun UI's inclusive full-day datetime filter."""
    text = value.isoformat()
    return [f"{text} 00:00:00", f"{text} 23:59:59"]


class JianDaoYunMCPWorkshopAdapter:
    def __init__(
        self,
        settings: Settings,
        client: ReadOnlyJianDaoYunMCPClient | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or ReadOnlyJianDaoYunMCPClient(
            settings.jiandaoyun_mcp_url,
            timeout_seconds=settings.jiandaoyun_mcp_timeout_seconds,
            retry_max_attempts=getattr(settings, "jiandaoyun_retry_max_attempts", 4),
        )
        self.data_api = JianDaoYunDataAPI(self.client)
        self._now = now or (lambda: datetime.now(ZoneInfo(settings.app_timezone)))
        self.used_snapshot = False

    def fetch_records(self, *, department: str, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]:
        department = scope.require(department) if scope else _require_department(department)
        return self._fetch_cached(department=department, mode="yesterday")

    def fetch_overdue_records(self, *, department: str, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]:
        department = scope.require(department) if scope else _require_department(department)
        current_date = self._now().astimezone(ZoneInfo(self.settings.app_timezone)).date()
        return [
            record for record in self._fetch_cached(department=department, mode="overdue")
            if record.process_status in {"待生产", "未生产"}
            and (
                record.planned_completion_at.date() < current_date
                or record.delivery_date < current_date
            )
        ]

    def fetch_plan_records(
        self, *, department: str, start_date: date, end_date: date, scope: DepartmentScope | None = None
    ) -> list[WorkshopProcessRecord]:
        department = scope.require(department) if scope else _require_department(department)
        mode = f"plan:{start_date.isoformat()}:{end_date.isoformat()}"
        records = self._fetch_cached(department=department, mode=mode)
        return [
            record for record in records
            if start_date <= record.planned_completion_at.date() <= end_date
        ]

    def fetch_order_records(self, *, department: str, product_order_no: str, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]:
        department = scope.require(department) if scope else _require_department(department)
        wanted = product_order_no.strip()
        if not wanted:
            raise AppError("WORKSHOP_ORDER_REQUIRED", "必须提供订单号", status_code=400)
        return run_query(
            connection_key=self.settings.jiandaoyun_mcp_url,
            query_key=f"order-detail|{department}|{wanted}",
            max_concurrency=getattr(self.settings, "jiandaoyun_max_concurrency", 3),
            requests_per_second=getattr(self.settings, "jiandaoyun_requests_per_second", 2.0),
            singleflight=getattr(self.settings, "jiandaoyun_singleflight_enabled", True),
            operation=lambda: run_async_blocking(lambda: self._fetch_order_records(department, wanted)),
        )

    async def _fetch_order_records(self, department: str, product_order_no: str) -> list[WorkshopProcessRecord]:
        rows = await self.data_api.list_records(
            app_id=self.settings.jiandaoyun_workshop_app_id,
            entry_id=self.settings.jiandaoyun_workshop_entry_id,
            fields=[*FIELDS.values(), "createTime", "updateTime"],
            conditions=[
                {"field": FIELDS["department"], "type": "text", "method": "eq", "value": [department]},
                {"field": FIELDS["product_order_no"], "type": "text", "method": "eq", "value": [product_order_no]},
            ],
        )
        report_date = datetime.now(ZoneInfo(self.settings.app_timezone)).date()
        return [self._map_row(row, report_date) for row in rows]

    def _fetch_cached(self, *, department: str, mode: str) -> list[WorkshopProcessRecord]:
        report_date = self._now().astimezone(ZoneInfo(self.settings.app_timezone)).date() - timedelta(days=1)
        snapshot_path = self._snapshot_path(department, report_date, mode)
        if getattr(self.settings, "workshop_realtime_query_enabled", True):
            self.used_snapshot = False
            query_key = "|".join((
                self.settings.jiandaoyun_workshop_app_id,
                self.settings.jiandaoyun_workshop_entry_id,
                department,
                mode,
            ))
            try:
                records = run_query(
                    connection_key=self.settings.jiandaoyun_mcp_url,
                    query_key=query_key,
                    max_concurrency=getattr(self.settings, "jiandaoyun_max_concurrency", 3),
                    requests_per_second=getattr(self.settings, "jiandaoyun_requests_per_second", 2.0),
                    singleflight=getattr(self.settings, "jiandaoyun_singleflight_enabled", True),
                    operation=lambda: run_async_blocking(
                        lambda: self._fetch_records(department=department, mode=mode)
                    ),
                )
            except AppError as exc:
                if exc.code not in {
                    "JIANDAOYUN_MCP_TIMEOUT", "JIANDAOYUN_MCP_UNAVAILABLE",
                    "JIANDAOYUN_MCP_RATE_LIMITED",
                } or not snapshot_path.is_file():
                    raise
                try:
                    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                    records = [WorkshopProcessRecord.model_validate(item) for item in payload]
                except (OSError, ValueError, TypeError) as cache_exc:
                    raise exc from cache_exc
                self.used_snapshot = True
                return records
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = snapshot_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps([record.model_dump(mode="json") for record in records], ensure_ascii=False),
                encoding="utf-8",
            )
            temporary.replace(snapshot_path)
            return records
        cache_key = (
            self.settings.jiandaoyun_workshop_app_id,
            self.settings.jiandaoyun_workshop_entry_id,
            report_date,
            f"{department}:{mode}",
        )
        with _CACHE_LOCK:
            cached = _RECORD_CACHE.get(cache_key)
            if cached is not None:
                return list(cached)
            if snapshot_path.is_file() and time.time() - snapshot_path.stat().st_mtime < 900:
                try:
                    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                    records = [WorkshopProcessRecord.model_validate(item) for item in payload]
                except (OSError, ValueError, TypeError):
                    pass
                else:
                    self.used_snapshot = True
                    _RECORD_CACHE[cache_key] = list(records)
                    return records
            # Serialize the first daily load so simultaneous bot messages do not
            # trigger duplicate full-table reads.
            try:
                records = run_async_blocking(
                    lambda: self._fetch_records(department=department, mode=mode)
                )
            except AppError as exc:
                if exc.code != "JIANDAOYUN_MCP_UNAVAILABLE" or not snapshot_path.is_file():
                    raise
                try:
                    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                    records = [WorkshopProcessRecord.model_validate(item) for item in payload]
                    self.used_snapshot = True
                except (OSError, ValueError, TypeError) as cache_exc:
                    raise exc from cache_exc
            else:
                snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = snapshot_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps([record.model_dump(mode="json") for record in records], ensure_ascii=False),
                    encoding="utf-8",
                )
                temporary.replace(snapshot_path)
            _RECORD_CACHE[cache_key] = list(records)
        return records

    def _snapshot_path(self, department: str, report_date: date, mode: str) -> Path:
        safe_department = re.sub(r"[^\w-]", "_", department)[:50] or "all"
        safe_mode = re.sub(r"[^\w-]", "_", mode)[:80]
        return (
            Path(self.settings.workshop_report_output_dir).resolve()
            / "cache"
            / f"{safe_department}-{report_date.isoformat()}-{safe_mode}.json"
        )

    async def _fetch_records(self, *, department: str = "", mode: str = "yesterday") -> list[WorkshopProcessRecord]:
        report_date = self._now().astimezone(ZoneInfo(self.settings.app_timezone)).date() - timedelta(days=1)
        base_conditions = []
        if department:
            base_conditions.append({
                    "field": FIELDS["department"],
                    "type": "text",
                    "method": "eq",
                    "value": [department],
                })
        if mode == "yesterday":
            condition_sets = [[*base_conditions, {
                "field": FIELDS["reported_at"], "type": "datetime", "method": "range",
                "value": _day_range(report_date),
            }]]
        elif mode == "overdue":
            pending = {
                "field": FIELDS["process_status"], "type": "text", "method": "in",
                "value": ["待生产", "未生产"],
            }
            # JianDaoYun date comparisons on these form fields are not reliable.
            # Fetch pending rows once, then enforce both date rules locally.
            condition_sets = [[*base_conditions, pending]]
        elif mode.startswith("plan:"):
            _, start_text, end_text = mode.split(":", 2)
            condition_sets = [[*base_conditions, {
                "field": FIELDS["planned_completion_at"], "type": "datetime", "method": "range",
                "value": [f"{start_text} 00:00:00", f"{end_text} 23:59:59"],
            }]]
        else:
            raise AppError("JIANDAOYUN_MCP_QUERY_MODE_INVALID", "简道云查询模式无效", status_code=500)
        row_map: dict[str, dict[str, Any]] = {}
        for conditions in condition_sets:
            rows = await self.data_api.list_records(
                app_id=self.settings.jiandaoyun_workshop_app_id,
                entry_id=self.settings.jiandaoyun_workshop_entry_id,
                fields=[*FIELDS.values(), "createTime", "updateTime"],
                conditions=conditions,
            )
            row_map.update({str(row.get("_id")): row for row in rows if row.get("_id")})
        return [self._map_row(row, report_date) for row in row_map.values()]

    def _map_row(self, row: dict[str, Any], report_date: date) -> WorkshopProcessRecord:
        tz = ZoneInfo(self.settings.app_timezone)
        reported_at = _datetime_value(row.get(FIELDS["reported_at"]), tz)
        submitted_at = _datetime_value(row.get("createTime"), tz) or reported_at
        planned = _datetime_value(row.get(FIELDS["planned_completion_at"]), tz)
        delivery = _date_value(row.get(FIELDS["delivery_date"])) or report_date
        order_date = _date_value(row.get(FIELDS["order_date"])) or min(report_date, delivery)
        status = _status_value(row.get(FIELDS["process_status"]))
        completion = _number(row.get(FIELDS["completion_rate"]))
        if completion > 1:
            completion /= 100
        completion = 1.0 if status == "已完成" else max(0.0, min(1.0, completion))
        measure = max(0.0, _number(row.get(FIELDS["measure"])))
        reporter = _person_name(row.get(FIELDS["reporter_name"]))
        if reported_at and not reporter:
            reporter = "简道云用户"
        if reported_at and submitted_at and reported_at < submitted_at:
            submitted_at = reported_at
        return WorkshopProcessRecord(
            source_record_id=_required(row.get("_id"), "数据编号"),
            order_code=_required(row.get(FIELDS["order_code"]), "订单号编码"),
            product_order_no=_required(row.get(FIELDS["product_order_no"]), "产品订单号"),
            picking_no=_text(row.get(FIELDS["picking_no"])),
            salesperson=_person_name(row.get(FIELDS["salesperson"])),
            workshop=_required(row.get(FIELDS["workshop"]), "车间"),
            order_date=order_date,
            delivery_date=max(delivery, order_date),
            product_name=_required(row.get(FIELDS["product_name"]), "产品名称"),
            product_quantity=max(0, int(_number(row.get(FIELDS["product_quantity"])))),
            total_meters=round(measure / 100, 2),
            total_centimeters=measure,
            color=_text(row.get(FIELDS["color"])),
            process_department=_required(row.get(FIELDS["department"]), "工序部门"),
            process_name=_required(row.get(FIELDS["process_name"]), "工序名称"),
            process_status=status,
            reporter_name=reporter,
            reported_at=reported_at,
            completion_rate=completion,
            remark=_text(row.get(FIELDS["remark"])),
            customer_grade=_text(row.get(FIELDS["customer_grade"])),
            planned_completion_at=planned or datetime.combine(delivery, datetime.max.time(), tzinfo=tz),
            owner_name=_person_name(row.get(FIELDS["owner"])) or reporter,
            submitted_at=submitted_at or datetime.combine(order_date, datetime.min.time(), tzinfo=tz),
            source_type="erp",
        )


def _require_department(department: str) -> str:
    value = department.strip()
    if not value:
        raise AppError("WORKSHOP_DEPARTMENT_REQUIRED", "必须指定业务部门", status_code=400)
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(filter(None, (_text(item) for item in value)))
    if isinstance(value, dict):
        return _person_name(value)
    return str(value).strip()


def _required(value: Any, label: str) -> str:
    result = _text(value)
    if not result:
        raise AppError("JIANDAOYUN_MCP_RECORD_INVALID", f"简道云记录缺少{label}", status_code=502)
    return result


def _person_name(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(filter(None, (_person_name(item) for item in value)))
    if isinstance(value, dict):
        for key in ("name", "nickname", "username", "text"):
            if value.get(key):
                return str(value[key]).strip()
        return ""
    return "" if value is None else str(value).strip()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date_value(value: Any) -> date | None:
    parsed = _datetime_value(value, ZoneInfo("Asia/Shanghai"))
    return parsed.date() if parsed else None


def _datetime_value(value: Any, tz: ZoneInfo) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(timestamp, tz=tz)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return parsed.replace(tzinfo=tz) if parsed.tzinfo is None else parsed.astimezone(tz)


def _status_value(value: Any) -> str:
    text = _text(value)
    aliases = {
        "未开始": "待生产",
        "进行中": "生产中",
        "已完工": "已完成",
        "取消": "已取消",
        "暂停": "已取消",
        "已暂停": "已取消",
    }
    text = aliases.get(text, text)
    return text if text in {"待生产", "未生产", "生产中", "已完成", "已取消"} else "待生产"
