from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.workshop.models import WorkshopProcessRecord

METER_UNIT = "米"
CENTIMETER_UNIT = "公分"
PIECE_UNIT = "件"


PENDING_STATUSES = {"待生产", "未生产"}
IN_PROGRESS_STATUSES = {"生产中"}
COMPLETED_STATUSES = {"已完成", "已完工"}


class WorkshopWorkReportRecord(BaseModel):
    """One row from the workshop work-report form."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_record_id: str = Field(min_length=1, max_length=100)
    source_form_name: str = Field(default="车间工序—报工", min_length=1, max_length=100)
    product_order_no: str = Field(min_length=1, max_length=100)
    salesperson: str = Field(default="", max_length=200)
    workshop: str = Field(min_length=1, max_length=200)
    order_date: date
    delivery_date: date
    product_name: str = Field(min_length=1, max_length=300)
    product_quantity: int = Field(default=0, ge=0)
    planned_quantity: float = Field(ge=0)
    completed_quantity: float = Field(ge=0)
    quantity_unit: Literal["米", "公分", "件"]
    color: str = Field(default="", max_length=300)
    process_name: str = Field(min_length=1, max_length=200)
    process_status: str = Field(min_length=1, max_length=50)
    scheduled_at: datetime | None = None
    report_department: str = Field(min_length=1, max_length=200)
    reportable_process: str = Field(default="", max_length=200)
    reporter_name: str = Field(min_length=1, max_length=200)
    reported_at: datetime
    completion_rate: float = Field(ge=0, le=1)
    remark: str = Field(default="", max_length=2000)
    submitted_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_record(self):
        if self.delivery_date < self.order_date:
            raise ValueError("delivery_date cannot be before order_date")
        if self.updated_at < self.submitted_at:
            raise ValueError("updated_at cannot be before submitted_at")
        if self.completed_quantity > self.planned_quantity and self.planned_quantity > 0:
            raise ValueError("completed_quantity cannot exceed planned_quantity")
        return self


def _business_key(record: WorkshopProcessRecord) -> tuple[str, str, str]:
    return record.product_order_no, record.process_department, record.process_name


def _report_key(record: WorkshopWorkReportRecord) -> tuple[str, str, str]:
    return record.product_order_no, record.report_department, record.process_name


def _is_quality_inspection_process(process_name: str) -> bool:
    return "质检" in (process_name or "")


def _deduplicate_plan(records: list[WorkshopProcessRecord]) -> list[WorkshopProcessRecord]:
    latest: dict[tuple[str, str, str], WorkshopProcessRecord] = {}
    for record in records:
        key = _business_key(record)
        current = latest.get(key)
        if current is None or (record.submitted_at, record.source_record_id) > (
            current.submitted_at,
            current.source_record_id,
        ):
            latest[key] = record
    return list(latest.values())


def _deduplicate_reports(records: list[WorkshopWorkReportRecord]) -> list[WorkshopWorkReportRecord]:
    latest: dict[str, WorkshopWorkReportRecord] = {}
    for record in records:
        current = latest.get(record.source_record_id)
        if current is None or record.updated_at > current.updated_at:
            latest[record.source_record_id] = record
    return list(latest.values())


def _is_important(record: WorkshopProcessRecord) -> bool:
    order_no = record.product_order_no.upper()
    return "JJ" in order_no or "YP" in order_no or record.customer_grade.upper() == "A"


def _is_overdue(record: WorkshopProcessRecord, current_date: date) -> bool:
    return record.process_status in PENDING_STATUSES and (
        record.planned_completion_at.date() < current_date or record.delivery_date < current_date
    )


def _plan_health(task_count: int, overdue_count: int) -> tuple[str, str]:
    if task_count == 0:
        return "暂无数据", "当前部门没有可统计的订单工序"
    overdue_rate = overdue_count / task_count
    if overdue_count == 0:
        return "进度平稳", "当前没有延期订单工序"
    if overdue_rate <= 0.1:
        return "需关注", "存在少量延期订单工序，请及时跟进"
    return "风险较高", "延期占比较高，请优先处理重点订单"


def _report_health(expected_count: int, report_rate: float) -> tuple[str, str]:
    if expected_count == 0:
        return "暂无数据", "当前部门没有应报工订单工序"
    if report_rate >= 0.9:
        return "良好", "报工覆盖率达到90%以上"
    if report_rate >= 0.7:
        return "需跟进", "仍有部分订单工序尚未报工"
    return "进度滞后", "报工覆盖率低于70%，请尽快核对"


def build_production_plan_summary(
    records: list[WorkshopProcessRecord],
    *,
    department: str,
    current_date: date,
    focus_limit: int = 5,
) -> dict[str, Any]:
    if not department.strip():
        raise ValueError("department is required")
    if not 1 <= focus_limit <= 20:
        raise ValueError("focus_limit must be between 1 and 20")

    selected = _deduplicate_plan(
        [
            r
            for r in records
            if r.process_department == department
            and not _is_quality_inspection_process(r.process_name)
        ]
    )
    focus_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    important_count = overdue_count = 0
    status_counts = {"待生产": 0, "生产中": 0, "已完成": 0, "其他": 0}
    for record in selected:
        important = _is_important(record)
        overdue = _is_overdue(record, current_date)
        important_count += int(important)
        overdue_count += int(overdue)
        if record.process_status in PENDING_STATUSES:
            status_counts["待生产"] += 1
        elif record.process_status in IN_PROGRESS_STATUSES:
            status_counts["生产中"] += 1
        elif record.process_status in COMPLETED_STATUSES:
            status_counts["已完成"] += 1
        else:
            status_counts["其他"] += 1
        if important or overdue:
            reasons = []
            if overdue:
                reasons.append("已延期")
            if important:
                reasons.append("重要订单")
            focus_rows.append(
                {
                    "product_order_no": record.product_order_no,
                    "process_name": record.process_name,
                    "process_status": record.process_status,
                    "total_meters": record.total_meters,
                    "planned_completion_at": record.planned_completion_at.isoformat(),
                    "delivery_date": record.delivery_date.isoformat(),
                    "owner_name": record.owner_name,
                    "risk_reason": "、".join(reasons),
                    "important": important,
                    "overdue": overdue,
                }
            )
        detail_rows.append(
            {
                "product_order_no": record.product_order_no,
                "process_name": record.process_name,
                "process_status": record.process_status,
                "product_name": record.product_name,
                "total_meters": record.total_meters,
                "total_centimeters": record.total_centimeters,
                "customer_grade": record.customer_grade,
                "planned_completion_at": record.planned_completion_at.isoformat(),
                "delivery_date": record.delivery_date.isoformat(),
                "owner_name": record.owner_name,
                "important": important,
                "overdue": overdue,
                "risk_reason": "、".join(
                    (["已延期"] if overdue else []) + (["重要订单"] if important else [])
                ) or "常规订单",
            }
        )

    focus_rows.sort(
        key=lambda row: (
            0 if row["important"] and row["overdue"] else 1 if row["overdue"] else 2,
            row["delivery_date"],
            row["product_order_no"],
            row["process_name"],
        )
    )
    detail_rows.sort(
        key=lambda row: (
            0 if row["important"] and row["overdue"] else 1 if row["overdue"] else 2 if row["important"] else 3,
            row["delivery_date"],
            row["product_order_no"],
            row["process_name"],
        )
    )
    task_count = len(selected)
    completed_rate = 0 if task_count == 0 else status_counts["已完成"] / task_count
    pending_rate = 0 if task_count == 0 else status_counts["待生产"] / task_count
    overdue_rate = 0 if task_count == 0 else overdue_count / task_count
    health_status, health_summary = _plan_health(task_count, overdue_count)
    return {
        "report_type": "production_plan",
        "report_date": current_date.isoformat(),
        "department": department,
        "task_count": task_count,
        "pending_count": status_counts["待生产"],
        "in_progress_count": status_counts["生产中"],
        "completed_count": status_counts["已完成"],
        "other_status_count": status_counts["其他"],
        "overdue_count": overdue_count,
        "important_count": important_count,
        "completed_rate": round(completed_rate, 4),
        "pending_rate": round(pending_rate, 4),
        "overdue_rate": round(overdue_rate, 4),
        "health_status": health_status,
        "health_summary": health_summary,
        "focus_orders": focus_rows[:focus_limit],
        "focus_total": len(focus_rows),
        "rows": detail_rows,
        "attachment_required": True,
    }


def _to_centimeters(quantity: float, unit: str) -> float:
    if unit == METER_UNIT:
        return quantity * 100
    if unit == CENTIMETER_UNIT:
        return quantity
    return 0


def _display_quantity(quantity: float, unit: str) -> tuple[float, str]:
    if unit in {METER_UNIT, CENTIMETER_UNIT}:
        return round(_to_centimeters(quantity, unit), 2), CENTIMETER_UNIT
    return round(quantity, 2), unit


def build_work_report_summary(
    plan_records: list[WorkshopProcessRecord],
    report_records: list[WorkshopWorkReportRecord],
    *,
    department: str,
    report_date: date,
    timezone: str = "Asia/Shanghai",
    top_limit: int = 5,
) -> dict[str, Any]:
    if not department.strip():
        raise ValueError("department is required")
    if not 1 <= top_limit <= 20:
        raise ValueError("top_limit must be between 1 and 20")
    tz = ZoneInfo(timezone)
    start = datetime.combine(report_date, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    plans = _deduplicate_plan(
        [
            r
            for r in plan_records
            if r.process_department == department
            and not _is_quality_inspection_process(r.process_name)
        ]
    )
    candidate_reports = [
        r
        for r in report_records
        if r.report_department == department
        and start <= r.reported_at.astimezone(tz) < end
    ]
    excluded_quality_reports = [
        r for r in candidate_reports if _is_quality_inspection_process(r.process_name)
    ]
    raw_reports = [
        r for r in candidate_reports if not _is_quality_inspection_process(r.process_name)
    ]
    reports = _deduplicate_reports(raw_reports)
    expected_keys = {_business_key(r) for r in plans}
    unmatched_keys = {_report_key(r) for r in reports} - expected_keys
    matched_reports = [r for r in reports if _report_key(r) in expected_keys]
    reported_keys = {_report_key(r) for r in reports}
    matched_reported_keys = {_report_key(r) for r in matched_reports}
    completed_order_numbers = {r.product_order_no for r in reports}

    people: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"completed_centimeters": 0.0, "completed_pieces": 0.0, "rate_sum": 0.0, "report_count": 0}
    )
    for record in reports:
        person = people[record.reporter_name]
        person["completed_centimeters"] += _to_centimeters(record.completed_quantity, record.quantity_unit)
        if record.quantity_unit == PIECE_UNIT:
            person["completed_pieces"] += record.completed_quantity
        person["rate_sum"] += record.completion_rate
        person["report_count"] += 1

    performers = []
    for name, values in people.items():
        rate = 0 if values["report_count"] == 0 else values["rate_sum"] / values["report_count"]
        performers.append(
            {
                "reporter_name": name,
                "completed_centimeters": round(values["completed_centimeters"], 2),
                "completed_pieces": round(values["completed_pieces"], 2),
                "completion_rate": round(rate, 4),
                "report_count": values["report_count"],
            }
        )
    performers.sort(
        key=lambda row: (
            -row["completed_centimeters"],
            -row["completed_pieces"],
            -row["completion_rate"],
            -row["report_count"],
            row["reporter_name"],
        )
    )
    for row in performers:
        if not row["completed_pieces"]:
            row.pop("completed_pieces")
    expected_count = len(expected_keys)
    reported_count = len(reported_keys)
    matched_reported_count = len(matched_reported_keys)
    report_rate = 0 if expected_count == 0 else round(matched_reported_count / expected_count, 4)
    health_status, health_summary = _report_health(expected_count, report_rate)
    completed_pieces = round(sum(r.completed_quantity for r in reports if r.quantity_unit == PIECE_UNIT), 2)
    raw_source_counts = Counter(r.source_form_name for r in candidate_reports)
    excluded_source_counts = Counter(r.source_form_name for r in excluded_quality_reports)
    source_names = list(dict.fromkeys(r.source_form_name for r in candidate_reports))
    source_record_breakdown = [
        {
            "form_name": source_name,
            "raw_record_count": raw_source_counts[source_name],
            "excluded_quality_inspection_record_count": excluded_source_counts[source_name],
            "included_record_count": raw_source_counts[source_name] - excluded_source_counts[source_name],
        }
        for source_name in source_names
    ]
    payload = {
        "report_type": "work_report",
        "report_date": report_date.isoformat(),
        "timezone": timezone,
        "department": department,
        "expected_count": expected_count,
        "reported_count": reported_count,
        "matched_reported_count": matched_reported_count,
        "pending_report_count": max(expected_count - matched_reported_count, 0),
        "report_rate": report_rate,
        "health_status": health_status,
        "health_summary": health_summary,
        "completed_order_count": len(completed_order_numbers),
        "completed_centimeters": round(sum(_to_centimeters(r.completed_quantity, r.quantity_unit) for r in reports), 2),
        "top_performers": performers[:top_limit],
        "performer_total": len(performers),
        "performers": performers,
        "rows": [
            {
                "product_order_no": r.product_order_no,
                "process_name": r.process_name,
                "process_status": r.process_status,
                "reporter_name": r.reporter_name,
                "reported_at": r.reported_at.isoformat(),
                "planned_quantity": _display_quantity(r.planned_quantity, r.quantity_unit)[0],
                "completed_quantity": _display_quantity(r.completed_quantity, r.quantity_unit)[0],
                "quantity_unit": _display_quantity(r.completed_quantity, r.quantity_unit)[1],
                "completion_rate": r.completion_rate,
                "matched": _report_key(r) in expected_keys,
                "remark": r.remark,
            }
            for r in reports
        ],
        "report_record_count_before_exclusions": len(candidate_reports),
        "report_record_count": len(raw_reports),
        "excluded_quality_inspection_record_count": len(excluded_quality_reports),
        "source_record_breakdown": source_record_breakdown,
        "deduplicated_report_record_count": len(reports),
        "matched_report_record_count": len(matched_reports),
        "unmatched_report_record_count": len(reports) - len(matched_reports),
        "unmatched_report_count": len(unmatched_keys),
        "attachment_required": True,
    }
    if completed_pieces:
        payload["completed_pieces"] = completed_pieces
    return payload


def _card_text(value: object, *, limit: int = 80) -> str:
    text = " ".join(str(value if value not in (None, "") else "-").split())
    for marker in ("\\", "*", "_", "`", "~", "[", "]", "<", ">"):
        text = text.replace(marker, f"\\{marker}")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_production_plan_card(payload: dict[str, Any], image_key: str | None = None) -> dict[str, Any]:
    overdue = int(payload.get("overdue_count", 0) or 0)
    template = "red" if overdue else "orange" if payload.get("important_count") else "green"
    focus_lines = []
    for index, row in enumerate(payload.get("focus_orders", []), start=1):
        focus_lines.append(
            f"{index}. **{_card_text(row.get('product_order_no'), limit=35)}**｜"
            f"{_card_text(row.get('process_name'), limit=25)}｜"
            f"{_card_text(row.get('process_status'), limit=15)}｜"
            f"计划完成 {_card_text(row.get('planned_completion_at'), limit=25)}｜"
            f"{_card_text(row.get('risk_reason'), limit=30)}"
        )
    if not focus_lines:
        focus_lines.append("暂无重要或延期订单")
    attachment_note = (
        "卡片仅展示前几条重点订单；完整订单和异常原因见 Excel 附件。"
        if payload.get("attachment_ready")
        else "卡片仅展示前几条重点订单；完整 Excel 明细尚未生成。"
    )
    elements: list[dict[str, Any]] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"📅 **统计日期**：{_card_text(payload.get('report_date'))}"}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": "### 📊 整体情况"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": (
            f"**{_card_text(payload.get('health_status'), limit=20)}**｜"
            f"{_card_text(payload.get('health_summary'), limit=80)}\n"
            f"完成占比：**{float(payload.get('completed_rate', 0) or 0):.2%}**　"
            f"待生产占比：**{float(payload.get('pending_rate', 0) or 0):.2%}**　"
            f"延期占比：**{float(payload.get('overdue_rate', 0) or 0):.2%}**"
        )}},
        {"tag": "div", "text": {"tag": "lark_md", "content": (
            f"订单工序总数：**{int(payload.get('task_count', 0) or 0)}**　"
            f"待生产：**{int(payload.get('pending_count', 0) or 0)}**　"
            f"生产中：**{int(payload.get('in_progress_count', 0) or 0)}**　"
            f"已完成：**{int(payload.get('completed_count', 0) or 0)}**\n"
            f"延期订单：**{overdue}**　重要订单：**{int(payload.get('important_count', 0) or 0)}**"
        )}},
        {"tag": "div", "text": {"tag": "lark_md", "content": "### 🚨 重点订单"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(focus_lines)}},
    ]
    if image_key:
        elements.append({"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": "车间生产计划日报完整图片"}, "mode": "fit_horizontal", "preview": True})
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": attachment_note}]})
    return {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": f"车间生产计划日报｜{_card_text(payload.get('department'), limit=30)}"},
        },
        "elements": elements,
    }


def build_work_report_card(payload: dict[str, Any], image_key: str | None = None) -> dict[str, Any]:
    performers = []
    for index, row in enumerate(payload.get("top_performers", []), start=1):
        amount = f"{float(row.get('completed_centimeters', 0) or 0):.2f}公分"
        if row.get("completed_pieces"):
            amount += f" / {float(row['completed_pieces']):.0f}件"
        performers.append(
            f"{index}. **{_card_text(row.get('reporter_name'), limit=25)}**｜"
            f"完成量 {amount}｜完成率 {float(row.get('completion_rate', 0) or 0):.2%}｜"
            f"报工 {int(row.get('report_count', 0) or 0)} 条"
        )
    if not performers:
        performers.append("昨日暂无有效报工人员数据")
    source_lines = [
        f"{_card_text(row.get('form_name'), limit=30)}："
        f"{int(row.get('raw_record_count', 0) or 0)} - "
        f"{int(row.get('excluded_quality_inspection_record_count', 0) or 0)} = "
        f"{int(row.get('included_record_count', 0) or 0)}"
        for row in payload.get("source_record_breakdown", [])
    ]
    rate = float(payload.get("report_rate", 0) or 0)
    template = "green" if rate >= 0.9 else "orange" if rate >= 0.7 else "red"
    attachment_note = (
        "排名以完成公分数为主、完成率为辅；米统一换算为公分，件数单独展示。完整明细见 Excel 附件。"
        if payload.get("attachment_ready")
        else "排名以完成公分数为主、完成率为辅；米统一换算为公分，件数单独展示。完整 Excel 明细尚未生成。"
    )
    elements: list[dict[str, Any]] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"📅 **统计日期**：{_card_text(payload.get('report_date'))}"}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": "### 📊 报工情况"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": (
            f"**{_card_text(payload.get('health_status'), limit=20)}**｜"
            f"{_card_text(payload.get('health_summary'), limit=80)}"
        )}},
        {"tag": "div", "text": {"tag": "lark_md", "content": (
            f"有效报工记录：**{int(payload.get('report_record_count', 0) or 0)}**　"
            f"去重后参与统计：**{int(payload.get('deduplicated_report_record_count', 0) or 0)}**　"
            f"应报工订单工序：**{int(payload.get('expected_count', 0) or 0)}**　"
            f"报工表实际订单工序：**{int(payload.get('reported_count', 0) or 0)}**　"
            f"匹配计划工序：**{int(payload.get('matched_reported_count', 0) or 0)}**　"
            f"未报工订单工序：**{int(payload.get('pending_report_count', 0) or 0)}**\n"
            f"报工率：**{rate:.2%}**　完成订单数：**{int(payload.get('completed_order_count', 0) or 0)}**　"
            f"昨日完成：**{float(payload.get('completed_centimeters', 0) or 0):.2f}公分**"
        )}},
        {"tag": "div", "text": {"tag": "lark_md", "content": (
            "### 🧮 报工记录口径\n"
            + ("\n".join(source_lines) if source_lines else "暂无报工来源明细")
            + f"\n合计：{int(payload.get('report_record_count_before_exclusions', 0) or 0)} - "
            + f"{int(payload.get('excluded_quality_inspection_record_count', 0) or 0)} = "
            + f"**{int(payload.get('report_record_count', 0) or 0)} 条**"
        )}},
        {"tag": "div", "text": {"tag": "lark_md", "content": "### 🏅 报工表现"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(performers)}},
        {"tag": "div", "text": {"tag": "lark_md", "content": "### ⚠️ 待处理"}},
        {"tag": "div", "text": {"tag": "lark_md", "content": (
            f"• 未报工订单工序：{int(payload.get('pending_report_count', 0) or 0)}\n"
            f"• 无法匹配计划工序的报工记录：{int(payload.get('unmatched_report_record_count', 0) or 0)} 条，涉及工序：{int(payload.get('unmatched_report_count', 0) or 0)} 个"
        )}},
    ]
    if image_key:
        elements.append({"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": "车间报工日报完整图片"}, "mode": "fit_horizontal", "preview": True})
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": attachment_note}]})
    return {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": f"车间报工日报｜{_card_text(payload.get('department'), limit=30)}"},
        },
        "elements": elements,
    }
