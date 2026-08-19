from __future__ import annotations

from typing import Any


GRADE_MARKS = {"A": "🟥 A", "B": "🟧 B", "C": "🟨 C", "D": "🟦 D", "E": "⬜ E"}


def _grade(value: object) -> str:
    grade = str(value or "-").strip().upper()
    return GRADE_MARKS.get(grade, grade)


def _rate(value: float | None) -> str:
    return "暂无" if value is None else f"{value:.1%}"


def _order_table(items: list[dict[str, Any]], *, important: bool = False, limit: int = 3) -> str:
    if not items:
        return "暂无相关订单"
    header = "| 订单号 | 等级 | 状态 | 总公分 | 未完成工序 | 优先级/说明 |\n| --- | --- | --- | ---: | --- | --- |"
    rows = []
    for row in items[:limit]:
        explanation = row.get("important_reason", "-") if important else row.get("incomplete_processes", "-")
        rows.append(
            f"| {row['product_order_no']} | {_grade(row.get('customer_grade'))} | "
            f"{'已完工' if row['complete'] else '待完工'} | {row['centimeters']:.0f} | "
            f"{row.get('incomplete_processes', '-') if not row.get('complete') else '-'} | {explanation} |"
        )
    return "\n".join((header, *rows))


def render_department_report_markdown(payload: dict[str, Any], *, source_label: str) -> str:
    total_rate = _rate(payload["completion_rate"])
    delayed_rate = _rate(payload["delayed_completion_rate"])
    regular_rate = _rate(payload["regular_completion_rate"])
    limit = int(payload.get("example_limit", 3))
    delayed_examples = payload.get("delayed_example_orders", payload["delayed_open_orders"][:limit])
    important_examples = payload.get("important_example_orders", payload["important_orders"][:limit])
    delayed_table = _order_table(delayed_examples, limit=limit)
    important_table = _order_table(important_examples, important=True, limit=limit)
    recommendations = payload.get("priority_recommendations", [])
    recommendation_lines = [
        f"| {index} | {row['product_order_no']} | {row['priority']} | "
        f"{row.get('incomplete_processes', '-')} | {row['recommendation']} |"
        for index, row in enumerate(recommendations[:10], start=1)
    ]
    recommendation_table = (
        "| 顺序 | 订单号 | 优先级 | 未完成工序 | 建议 |\n"
        "| ---: | --- | --- | --- | --- |\n" + "\n".join(recommendation_lines)
        if recommendation_lines else "当前没有未完成订单需要额外安排。"
    )
    completed = int(payload["completed_order_count"])
    total = int(payload["yesterday_plan_order_count"])
    open_delayed = int(payload["delayed_open_order_count"])
    excluded_count = int(payload.get("excluded_order_count", 0))
    excluded_numbers = payload.get("excluded_order_numbers", [])
    exclusion_note = ""
    if excluded_count:
        exclusion_note = (
            f"本次从原始去重订单 {payload.get('source_yesterday_plan_order_count', total)} 单中排除 "
            f"{excluded_count} 单（{', '.join(excluded_numbers)}）。"
        )
    if total == 0:
        insight = "该统计日期没有计划完成订单，我已保留空报表供你核对日期和部门。"
    elif open_delayed:
        insight = (
            f"昨日共 {total} 个订单，已完工 {completed} 个；目前还有 {open_delayed} 个待完工延期订单，"
            "建议优先跟进下方重要订单。"
        )
    else:
        insight = f"昨日共 {total} 个订单，已完工 {completed} 个，目前没有待完工延期订单。"
    if exclusion_note:
        insight = f"{insight} {exclusion_note}"

    message = (
        f"# {payload['department']}｜昨日订单日报\n"
        f"> 统计日期：**{payload['yesterday_date']}**｜报告生成：{payload['generated_at'].replace('T', ' ')}｜数据源：{source_label}\n\n"
        f"> 💡 {insight}\n\n"
        "## 📊 昨日完成情况概览\n"
        "| 订单总数 | 总公分 | 已完工公分 | 公分数完成率 |\n"
        "| ---: | ---: | ---: | ---: |\n"
        f"| **{payload['yesterday_plan_order_count']}** | **{payload['yesterday_plan_cm']:.0f}** | "
        f"**{payload['completed_cm']:.0f}** | **{total_rate}** |\n\n"
        "## ✅ 分类订单完成率\n"
        "| 分类 | 已完成 | 订单总数 | 订单完成率 |\n"
        "| --- | ---: | ---: | ---: |\n"
        f"| 延期订单 | {payload['delayed_completed_count']} | {payload['delayed_order_count']} | **{delayed_rate}** |\n"
        f"| 常规订单 | {payload['regular_completed_count']} | {payload['regular_order_count']} | **{regular_rate}** |\n\n"
        f"## ⚠️ 待完工延期订单（共 {payload['delayed_open_order_count']} 单，展示 {limit} 单）\n"
        f"{delayed_table}\n\n"
        f"## 🔶 重要订单（共 {len(payload['important_orders'])} 单，展示 {limit} 单）\n"
        f"{important_table}\n\n"
        f"> 重要订单口径：客户等级 A、公分数≥{payload.get('important_large_centimeters', 1000):g}、即将/已经延期，或订单号包含 JJ/YP；多个条件可同时命中。\n"
        "## 📌 优先处理建议\n"
        f"{recommendation_table}\n\n"
        "> 以上为日报中的处理建议，不会自动修改订单或代替人工下达生产指令。\n"
        "> 统计口径：按昨日计划完成日期及所选部门筛选；订单数和公分数均按订单编号去重，同一订单的多个工序只计算一次。"
    )
    if payload["empty"]:
        message += f"\n\n> {payload['department']} 在 {payload['yesterday_date']} 暂无计划完成订单。"
    return message
