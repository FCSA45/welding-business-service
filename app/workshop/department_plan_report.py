"""Department plan report based on planned completion dates and process status."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.workshop.models import WorkshopProcessRecord


COMPLETED_STATUSES = {"已完工", "已完成"}
PENDING_STATUSES = {"待生产", "未生产"}
EXCLUDED_ORDER_STATUSES = {"已取消", "已暂停"}
PRIORITY_RANK = {"重要订单": 0, "延期订单": 1, "常规订单": 2}


def _priority(rows: list[WorkshopProcessRecord], report_date: date) -> str:
    if any(
        "JJ" in row.product_order_no.upper()
        or "YP" in row.product_order_no.upper()
        or row.customer_grade.strip().upper() == "A"
        for row in rows
    ):
        return "重要订单"
    if any(
        row.process_status in PENDING_STATUSES
        and (row.planned_completion_at.date() < report_date or row.delivery_date < report_date)
        for row in rows
    ):
        return "延期订单"
    return "常规订单"


def _work_item_key(record: WorkshopProcessRecord) -> str:
    """Use the business product-order number, never an internal row/order code."""
    return record.product_order_no.strip() or record.order_code.strip()


def _excluded_order_keys(records: list[WorkshopProcessRecord]) -> set[str]:
    """Exclude orders whose complete process history is cancelled or paused."""
    grouped: dict[str, list[WorkshopProcessRecord]] = defaultdict(list)
    for record in records:
        grouped[_work_item_key(record)].append(record)
    return {
        order_key
        for order_key, rows in grouped.items()
        if rows and all(row.process_status in EXCLUDED_ORDER_STATUSES for row in rows)
    }


def _item_centimeters(rows: list[WorkshopProcessRecord]) -> float:
    """Count a sub-order length once, never once per process."""
    return max((float(row.total_centimeters or 0) for row in rows), default=0.0)


def _orders(
    records: list[WorkshopProcessRecord], report_date: date,
    *, important_large_centimeters: float = 1000.0,
) -> list[dict[str, Any]]:
    groups: dict[str, list[WorkshopProcessRecord]] = defaultdict(list)
    for record in records:
        groups[_work_item_key(record)].append(record)
    result = []
    for product_order_no, rows in groups.items():
        item_code = rows[0].picking_no.strip() or rows[0].product_name.strip()
        incomplete = [row for row in rows if row.process_status not in COMPLETED_STATUSES]
        priority = _priority(rows, report_date)
        reference_date = report_date.fromordinal(report_date.toordinal() - 1)
        delayed = any(
            row.planned_completion_at.date() < reference_date
            or row.delivery_date < reference_date
            for row in rows
        )
        centimeters = round(_item_centimeters(rows), 2)
        important_reasons: list[str] = []
        if any(row.customer_grade.strip().upper() == "A" for row in rows):
            important_reasons.append("客户等级A")
        if centimeters >= important_large_centimeters:
            important_reasons.append("公分数较大")
        if delayed:
            important_reasons.append("已经延期")
        elif any(row.delivery_date <= report_date for row in rows):
            important_reasons.append("即将延期")
        number = " ".join((product_order_no, rows[0].order_code)).upper()
        if "JJ" in number or "YP" in number:
            important_reasons.append("订单号含JJ/YP")
        result.append({
            "product_order_no": product_order_no,
            "source_order_codes": list(dict.fromkeys(row.order_code for row in rows)),
            "item_code": item_code,
            "product_name": rows[0].product_name,
            "planned_date": min(row.planned_completion_at.date().isoformat() for row in rows),
            "delivery_date": min(row.delivery_date.isoformat() for row in rows),
            "centimeters": centimeters,
            "incomplete_processes": "、".join(dict.fromkeys(row.process_name for row in incomplete)) or "-",
            "priority": priority,
            "statuses": "、".join(dict.fromkeys(row.process_status for row in rows)),
            "customer_grade": next((row.customer_grade for row in rows if row.customer_grade), ""),
            "complete": not incomplete,
            "delayed": delayed,
            "important": bool(important_reasons),
            "important_reason": "、".join(important_reasons),
        })
    return sorted(result, key=lambda row: (
        PRIORITY_RANK[row["priority"]], row["delivery_date"], row["planned_date"], row["product_order_no"]
    ))


def build_department_plan_payload(
    records: list[WorkshopProcessRecord], *, department: str, report_date: date,
    timezone: str = "Asia/Shanghai", important_large_centimeters: float = 1000.0,
    example_limit: int = 3,
) -> dict[str, Any]:
    yesterday = report_date.fromordinal(report_date.toordinal() - 1)
    scoped = [row for row in records if row.process_department == department]
    excluded_orders = _excluded_order_keys(scoped)
    yesterday_rows_before_exclusion = [
        row for row in scoped if row.planned_completion_at.date() == yesterday
    ]
    source_yesterday_order_keys = {
        _work_item_key(row) for row in yesterday_rows_before_exclusion
    }
    scoped = [row for row in scoped if _work_item_key(row) not in excluded_orders]
    yesterday_rows = [row for row in scoped if row.planned_completion_at.date() == yesterday]
    yesterday_item_groups: dict[str, list[WorkshopProcessRecord]] = defaultdict(list)
    for row in yesterday_rows:
        yesterday_item_groups[_work_item_key(row)].append(row)
    planned_cm = sum(_item_centimeters(rows) for rows in yesterday_item_groups.values())
    completed_cm = sum(
        _item_centimeters(rows) for rows in yesterday_item_groups.values()
        if all(row.process_status in COMPLETED_STATUSES for row in rows)
    )
    unfinished_cm = planned_cm - completed_cm
    yesterday_orders = _orders(
        yesterday_rows, report_date,
        important_large_centimeters=important_large_centimeters,
    )
    delayed_orders = [order for order in yesterday_orders if order["delayed"]]
    delayed_open_orders = [order for order in delayed_orders if not order["complete"]]
    regular_orders = [order for order in yesterday_orders if not order["delayed"]]
    important_orders = [order for order in yesterday_orders if order["important"]]
    priority_recommendations = []
    recommendation_candidates = [order for order in yesterday_orders if not order["complete"]]
    recommendation_candidates.sort(
        key=lambda order: (
            0 if order["important"] and order["delayed"] else
            1 if order["delayed"] else
            2 if order["important"] else 3,
            order["delivery_date"],
            order["planned_date"],
            order["product_order_no"],
        )
    )
    for order in recommendation_candidates:
        if order["priority"] == "重要订单" and order["delayed"]:
            reason = "重要且已延期，优先安排并立即跟进负责人"
        elif order["priority"] == "重要订单":
            reason = "重要订单，建议优先锁定生产资源"
        elif order["priority"] == "延期订单":
            reason = "已延期，建议先处理未完成工序"
        else:
            reason = "常规未完工订单，按计划顺序推进"
        priority_recommendations.append({
            "product_order_no": order["product_order_no"],
            "priority": order["priority"],
            "incomplete_processes": order["incomplete_processes"],
            "delivery_date": order["delivery_date"],
            "recommendation": reason,
        })
    example_limit = max(1, min(10, int(example_limit)))
    delayed_example_orders = delayed_open_orders[:example_limit]
    delayed_example_numbers = {order["product_order_no"] for order in delayed_example_orders}
    important_example_orders = [
        order for order in important_orders
        if order["product_order_no"] not in delayed_example_numbers
    ][:example_limit]
    process_groups: dict[str, list[WorkshopProcessRecord]] = defaultdict(list)
    for row in yesterday_rows:
        process_groups[row.process_name].append(row)
    process_stats = [{
        "process": name,
        "planned_cm": round(sum(float(row.total_centimeters or 0) for row in rows), 2),
        "completed_cm": round(sum(float(row.total_centimeters or 0) for row in rows if row.process_status in COMPLETED_STATUSES), 2),
        "unfinished_cm": round(sum(float(row.total_centimeters or 0) for row in rows if row.process_status not in COMPLETED_STATUSES), 2),
    } for name, rows in sorted(process_groups.items())]
    quality = [
        "订单数和公分数均按订单编号去重；同一订单的多个工序或领料记录只计算一次。",
    ]
    if any(row.process_status == "已完成" for row in scoped):
        quality.append("源数据使用“已完成”，业务口径使用“已完工”；本报告将两者统一视为完工状态。")
    return {
        "department": department, "report_date": report_date.isoformat(),
        "important_large_centimeters": important_large_centimeters,
        "example_limit": example_limit,
        "yesterday_date": yesterday.isoformat(), "timezone": timezone,
        "generated_at": datetime.now(ZoneInfo(timezone)).isoformat(timespec="seconds"),
        "source_yesterday_plan_order_count": len(source_yesterday_order_keys),
        "excluded_order_count": len(excluded_orders & source_yesterday_order_keys),
        "excluded_order_numbers": sorted(excluded_orders & source_yesterday_order_keys),
        "yesterday_plan_order_count": len(yesterday_orders),
        "yesterday_plan_cm": round(planned_cm, 2),
        "completed_cm": round(completed_cm, 2), "unfinished_cm": round(unfinished_cm, 2),
        "completion_rate": None if planned_cm == 0 else completed_cm / planned_cm,
        "completed_order_count": sum(order["complete"] for order in yesterday_orders),
        "unfinished_order_count": sum(not order["complete"] for order in yesterday_orders),
        "yesterday_unfinished_orders": [order for order in yesterday_orders if not order["complete"]],
        "delayed_order_count": len(delayed_orders),
        "delayed_completed_count": sum(order["complete"] for order in delayed_orders),
        "delayed_completion_rate": (
            None if not delayed_orders else sum(order["complete"] for order in delayed_orders) / len(delayed_orders)
        ),
        "regular_order_count": len(regular_orders),
        "regular_completed_count": sum(order["complete"] for order in regular_orders),
        "regular_completion_rate": (
            None if not regular_orders else sum(order["complete"] for order in regular_orders) / len(regular_orders)
        ),
        "delayed_orders": delayed_orders,
        "delayed_open_order_count": len(delayed_open_orders),
        "delayed_open_orders": delayed_open_orders,
        "important_orders": important_orders,
        "priority_recommendations": priority_recommendations[:10],
        "delayed_example_orders": delayed_example_orders,
        "important_example_orders": important_example_orders,
        "today_orders": [], "process_stats": process_stats, "data_quality": quality,
        "empty": not yesterday_rows,
    }


def write_department_plan_html(payload: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    rate = "暂无计划" if payload["completion_rate"] is None else f"{payload['completion_rate']:.1%}"
    quality = "".join(f"<li>{escape(item)}</li>" for item in payload["data_quality"])
    process_rows = "".join(
        f"<tr><td>{escape(row['process'])}</td><td>{row['planned_cm']:.2f}</td><td>{row['completed_cm']:.2f}</td><td>{row['unfinished_cm']:.2f}</td></tr>"
        for row in payload["process_stats"]
    ) or '<tr><td colspan="4">该部门暂无相关订单</td></tr>'
    def order_rows(items: list[dict[str, Any]]) -> str:
        rows = []
        for row in items:
            grade = str(row.get("customer_grade") or "-").strip().upper()
            grade_class = f"grade-{grade.lower()}" if grade in {"A", "B", "C", "D", "E"} else "grade-other"
            rows.append(
            f'<tr data-priority="{escape(row["priority"])}">'
            f'<td>{escape(row["product_order_no"])}</td><td><span class="grade {grade_class}">{escape(grade)}</span></td>'
            f'<td>{escape(row["planned_date"])}</td><td>{row["centimeters"]:.2f}</td>'
            f'<td>{escape(row["incomplete_processes"])}</td><td>{escape(row["delivery_date"])}</td>'
            f'<td><span class="pill {"p1" if row["priority"] == "重要订单" else "p2" if row["priority"] == "延期订单" else "p3"}">{escape(row["priority"])}</span></td>'
            f'<td>{escape(row["statuses"])}</td></tr>'
            )
        return "".join(rows) or '<tr><td colspan="8">该部门暂无相关订单</td></tr>'
    html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(payload['department'])}车间计划日报</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#f2f5f9;color:#173047;font-family:"Microsoft YaHei",sans-serif}}main{{max-width:1280px;margin:auto;padding:20px}}header,.panel{{background:#fff;border-radius:14px;padding:20px;margin-bottom:16px;box-shadow:0 2px 10px #17304710}}h1{{margin:0 0 8px;color:#173f73}}.issue{{background:#fff4d8;border-left:5px solid #e6a100}}.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}.kpi{{background:#eef5fb;border-radius:10px;padding:14px}}.kpi b{{display:block;font-size:24px;color:#175f9d;margin-top:5px}}.chart{{display:flex;height:28px;border-radius:8px;overflow:hidden;background:#dfe6ed}}.done{{background:#2e9d68}}.todo{{background:#e29a2d}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:820px}}th{{background:#173f73;color:#fff;cursor:pointer}}th,td{{padding:10px;border-bottom:1px solid #dce4eb;text-align:left}}.pill,.grade{{padding:3px 8px;border-radius:999px;white-space:nowrap;font-weight:700}}.p1{{background:#fde2e2;color:#b42318}}.p2{{background:#fff0d1;color:#a15c00}}.p3{{background:#e7eef5;color:#38536b}}.grade-a{{background:#f8696b;color:#fff}}.grade-b{{background:#f4b183;color:#713b00}}.grade-c{{background:#ffd966;color:#614b00}}.grade-d{{background:#9dc3e6;color:#173f73}}.grade-e{{background:#d9e1f2;color:#38536b}}.grade-other{{background:#e7eef5;color:#38536b}}.filters{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}}select{{padding:8px;border:1px solid #bdcad6;border-radius:7px}}footer{{color:#66788a;font-size:12px;padding:8px}}@media(max-width:600px){{main{{padding:10px}}header,.panel{{padding:14px}}}}
    </style></head><body><main><header><h1>{escape(payload['department'])}｜车间计划日报</h1><div>报告日期：{payload['report_date']}　昨日：{payload['yesterday_date']}　时区：{payload['timezone']}</div></header>
    <section class="panel issue"><b>数据质量检查</b><ul>{quality}</ul></section>
    {'<section class="panel"><b>该部门暂无相关订单</b></section>' if payload['empty'] else ''}
    <section class="panel"><h2>昨日完成 KPI</h2><div class="kpis"><div class="kpi">昨日计划订单<b>{payload['yesterday_plan_order_count']}</b></div><div class="kpi">计划总公分数<b>{payload['yesterday_plan_cm']:.2f}</b></div><div class="kpi">已完工公分数<b>{payload['completed_cm']:.2f}</b></div><div class="kpi">未完工公分数<b>{payload['unfinished_cm']:.2f}</b></div><div class="kpi">公分数完成率<b>{rate}</b></div><div class="kpi">完工/未完工订单<b>{payload['completed_order_count']} / {payload['unfinished_order_count']}</b></div></div></section>
    <section class="panel"><h2>昨日完工/未完工公分数</h2><div class="chart"><div class="done" style="width:{0 if not payload['yesterday_plan_cm'] else payload['completed_cm']/payload['yesterday_plan_cm']*100:.2f}%"></div><div class="todo" style="flex:1"></div></div></section>
    <section class="panel"><h2>按工序统计</h2><div class="table-wrap"><table><thead><tr><th>工序</th><th>计划公分数</th><th>完工公分数</th><th>未完工公分数</th></tr></thead><tbody>{process_rows}</tbody></table></div></section>
    <section class="panel"><h2>昨日未完工订单</h2><div class="table-wrap"><table class="sortable"><thead><tr><th>订单子单号</th><th>客户等级</th><th>计划完成</th><th>总公分数</th><th>待完成工序</th><th>交货日期</th><th>优先级</th><th>工序状态</th></tr></thead><tbody>{order_rows(payload['yesterday_unfinished_orders'])}</tbody></table></div></section>
    <section class="panel"><h2>今日计划订单</h2><div class="filters"><select id="priority"><option value="">全部优先级</option><option>重要订单</option><option>延期订单</option><option>常规订单</option></select></div><div class="table-wrap"><table id="today" class="sortable"><thead><tr><th>订单子单号</th><th>客户等级</th><th>计划完成</th><th>总公分数</th><th>待完成工序</th><th>交货日期</th><th>优先级</th><th>工序状态</th></tr></thead><tbody>{order_rows(payload['today_orders'])}</tbody></table></div></section>
    <footer>数据来源：车间工序基础表｜部门：{escape(payload['department'])}｜报告日期：{payload['report_date']}｜生成时间：{payload['generated_at']}<br>工作量处理：订单数和公分数均按订单编号去重；同一订单的多个工序或领料记录只计算一次。</footer></main>
    <script>document.querySelectorAll('.sortable th').forEach((th,i)=>th.onclick=()=>{{const tb=th.closest('table').tBodies[0];[...tb.rows].sort((a,b)=>a.cells[i].innerText.localeCompare(b.cells[i].innerText,'zh-CN',{{numeric:true}})).forEach(r=>tb.appendChild(r))}});function filter(){{const p=document.querySelector('#priority').value;document.querySelectorAll('#today tbody tr').forEach(r=>r.style.display=(!p||r.dataset.priority===p)?'':'none')}}document.querySelector('#priority').onchange=filter;</script></body></html>'''
    path.write_text(html, encoding="utf-8")
    return path
