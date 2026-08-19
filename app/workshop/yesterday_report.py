from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.workshop.models import WorkshopProcessRecord


PENDING_STATUSES = {"待生产", "未生产"}


def priority_of(record: WorkshopProcessRecord, current_date: date) -> str:
    order_upper = record.product_order_no.upper()
    if "JJ" in order_upper or "YP" in order_upper or record.customer_grade.upper() == "A":
        return "重要订单"
    if record.process_status in PENDING_STATUSES and (
        record.planned_completion_at.date() < current_date
        or record.delivery_date < current_date
    ):
        return "延期订单"
    return "常规订单"


def build_yesterday_report(
    records: list[WorkshopProcessRecord], *, current_date: date, timezone: str = "Asia/Shanghai",
    department: str = "", overdue_records: list[WorkshopProcessRecord] | None = None,
) -> dict:
    tz = ZoneInfo(timezone)
    report_date = current_date - timedelta(days=1)
    start = datetime.combine(report_date, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    selected = [
        r for r in records
        if r.reported_at
        and start <= r.reported_at.astimezone(tz) < end
        and (not department or r.process_department == department)
    ]
    priority_rank = {"重要订单": 0, "延期订单": 1, "常规订单": 2}
    rows = [{**r.model_dump(mode="json"), "priority": priority_of(r, current_date)} for r in selected]
    rows.sort(key=lambda r: (
        r["process_department"], r["process_name"], priority_rank[r["priority"]],
        r["delivery_date"], r["product_order_no"], r["source_record_id"],
    ))
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        groups[row["process_department"]][row["process_name"]].append(row)
    orders: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        orders[row["product_order_no"]].append(row)
    order_summaries = []
    for order_no, order_rows in orders.items():
        first = order_rows[0]
        statuses = {row["process_status"] for row in order_rows}
        status = "已完成" if statuses <= {"已完成"} else "生产中" if "生产中" in statuses else "待生产"
        planned_date = min(str(row["planned_completion_at"])[:10] for row in order_rows)
        delivery_date = min(str(row["delivery_date"])[:10] for row in order_rows)
        important = (
            "JJ" in order_no.upper() or "YP" in order_no.upper()
            or any(str(row.get("customer_grade", "")).upper() == "A" for row in order_rows)
            or planned_date > delivery_date
        )
        delayed_by_date = planned_date < current_date.isoformat() or delivery_date < current_date.isoformat()
        warning = planned_date == delivery_date and status == "生产中"
        order_summaries.append({
            "product_order_no": order_no,
            "product_name": first["product_name"],
            "product_quantity": max(int(row["product_quantity"]) for row in order_rows),
            "total_meters": max(float(row.get("total_meters") or 0) for row in order_rows),
            "customer_grade": first.get("customer_grade", ""),
            "planned_completion_date": planned_date,
            "delivery_date": delivery_date,
            "status": status,
            "reporter_name": first.get("reporter_name", ""),
            "reporter_names": "、".join(sorted({str(row.get("reporter_name") or "") for row in order_rows if row.get("reporter_name")})),
            "reported_at": max((str(row.get("reported_at") or "") for row in order_rows), default=""),
            "important": important,
            "delayed_by_date": delayed_by_date,
            "warning": warning,
        })
    daily_targets = [order for order in order_summaries if order["planned_completion_date"] == report_date.isoformat()]
    target_meters = sum(order["total_meters"] for order in daily_targets)
    completed_target_meters = sum(order["total_meters"] for order in daily_targets if order["status"] == "已完成")
    completed_delayed = [order for order in order_summaries if order["delayed_by_date"] and order["status"] == "已完成"]
    overdue_groups: dict[str, list[WorkshopProcessRecord]] = defaultdict(list)
    for record in overdue_records or []:
        overdue_groups[record.product_order_no].append(record)
    delayed_orders = []
    for order_no, backlog_rows in overdue_groups.items():
        first_record = backlog_rows[0]
        delayed_orders.append({
            "product_order_no": order_no,
            "product_name": first_record.product_name,
            "product_quantity": max(row.product_quantity for row in backlog_rows),
            "total_meters": max(float(row.total_meters or 0) for row in backlog_rows),
            "customer_grade": first_record.customer_grade,
            "planned_completion_date": min(row.planned_completion_at.date().isoformat() for row in backlog_rows),
            "delivery_date": min(row.delivery_date.isoformat() for row in backlog_rows),
            "status": "待生产",
            "reporter_name": "",
            "reporter_names": "",
            "reported_at": "",
            "important": any(priority_of(row, current_date) == "重要订单" for row in backlog_rows),
            "delayed_by_date": True,
            "warning": False,
        })
    open_order_numbers = {order["product_order_no"] for order in delayed_orders}
    completed_delayed = [order for order in completed_delayed if order["product_order_no"] not in open_order_numbers]
    delayed_pool = [*delayed_orders, *completed_delayed]
    common_orders = [order for order in order_summaries if not order["important"] and not order["delayed_by_date"]]
    important_orders = [order for order in order_summaries if order["important"] and order["status"] == "已完成"]
    warning_orders = [order for order in order_summaries if order["warning"]]
    completed_common = [order for order in common_orders if order["status"] == "已完成"]
    return {
        "report_date": report_date.isoformat(), "timezone": timezone, "department": department,
        "generated_for_date": current_date.isoformat(), "record_count": len(rows),
        "order_count": len({r["product_order_no"] for r in rows}),
        "total_product_quantity": sum(r["product_quantity"] for r in rows),
        "total_meters": round(sum(r["total_meters"] or 0 for r in rows), 2),
        "priority_counts": {name: sum(r["priority"] == name for r in rows) for name in priority_rank},
        "rows": rows,
        "groups": {department: dict(processes) for department, processes in groups.items()},
        "order_summaries": order_summaries,
        "estimated_target_meters": round(target_meters, 2),
        "completed_target_meters": round(completed_target_meters, 2),
        "meter_completion_rate": 0 if target_meters == 0 else completed_target_meters / target_meters,
        "delayed_order_count": len(delayed_pool),
        "delayed_open_count": len(delayed_orders),
        "delayed_completed_count": len(completed_delayed),
        "delayed_completion_rate": 0 if not delayed_pool else len(completed_delayed) / len(delayed_pool),
        "common_order_count": len(common_orders),
        "common_completed_count": len(completed_common),
        "common_on_time_rate": 0 if not common_orders else sum(order["status"] == "已完成" and order["planned_completion_date"] <= order["delivery_date"] for order in common_orders) / len(common_orders),
        "completed_order_count": sum(order["status"] == "已完成" for order in order_summaries),
        "important_orders": important_orders,
        "delayed_orders": delayed_orders,
        "warning_orders": warning_orders,
    }
