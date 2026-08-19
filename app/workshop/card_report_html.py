from __future__ import annotations

from html import escape
from typing import Any


def _text(value: object) -> str:
    return escape(str(value if value not in (None, "") else "-"))


def _percent(value: object) -> str:
    return f"{float(value or 0):.2%}"


def _base_style() -> str:
    return """
    *{box-sizing:border-box}body{margin:0;background:#f5f3ee;color:#3d392f;font-family:"Microsoft YaHei","PingFang SC",sans-serif}
    main{width:1160px;margin:0 auto;padding:42px 34px 52px}h1{text-align:center;margin:0;color:#7b2f22;font-size:34px;letter-spacing:2px}
    .meta{text-align:center;color:#8a9577;margin:9px 0 24px;font-size:13px}.summary{background:#fff;border-left:5px solid #9acb8f;border-radius:7px;padding:18px 22px;box-shadow:0 2px 8px #0000000c;line-height:1.9}
    .summary strong{color:#7b2f22;font-size:18px}.section{margin-top:25px}.section-title{font-size:19px;font-weight:700;border-left:4px solid #a8d49e;padding-left:10px;margin-bottom:12px;color:#563a2d}
    .metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.metric{background:#fff;border:1px solid #e7e2d8;border-radius:7px;padding:15px}.metric span{display:block;color:#817b6e;font-size:13px}.metric b{display:block;margin-top:7px;font-size:24px;color:#7b2f22}
    table{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border-radius:7px;overflow:hidden;box-shadow:0 2px 8px #0000000c;font-size:13px}
    th{background:#716a49;color:#fff;padding:11px 9px;text-align:left}td{padding:10px 9px;border-bottom:1px solid #ece8df;vertical-align:top}tbody tr:nth-child(even){background:#faf9f6}
    .danger{color:#b42318;font-weight:700}.warn{color:#b26a00;font-weight:700}.good{color:#2f7d32;font-weight:700}.empty{text-align:center;color:#8a857a;padding:30px}
    footer{text-align:center;color:#a19b8d;font-size:12px;margin-top:30px}
    """


def build_production_plan_html(payload: dict[str, Any]) -> str:
    rows = payload.get("rows", [])
    body = "".join(
        "<tr>"
        f"<td>{_text(row.get('product_order_no'))}</td>"
        f"<td>{_text(row.get('product_name'))}</td>"
        f"<td>{_text(row.get('process_name'))}</td>"
        f"<td>{_text(row.get('process_status'))}</td>"
        f"<td>{_text(row.get('total_meters'))}</td>"
        f"<td>{_text(row.get('customer_grade'))}</td>"
        f"<td>{_text(row.get('planned_completion_at'))}</td>"
        f"<td>{_text(row.get('delivery_date'))}</td>"
        f"<td class={'danger' if row.get('overdue') else 'warn' if row.get('important') else 'good'}>{_text(row.get('risk_reason'))}</td>"
        "</tr>"
        for row in rows
    ) or '<tr><td class="empty" colspan="9">当前部门没有订单工序数据</td></tr>'
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>{_base_style()}</style></head><body><main>
    <h1>车间生产计划日报</h1><div class="meta">统计日期：{_text(payload.get('report_date'))} ｜ 部门：{_text(payload.get('department'))}</div>
    <div class="summary">📋 当前整体状态为 <strong>{_text(payload.get('health_status'))}</strong>。{_text(payload.get('health_summary'))}；
    完成占比 <b>{_percent(payload.get('completed_rate'))}</b>，待生产占比 <b>{_percent(payload.get('pending_rate'))}</b>，延期占比 <b>{_percent(payload.get('overdue_rate'))}</b>。</div>
    <section class="section"><div class="section-title">📊 整体情况</div><div class="metrics">
    <div class="metric"><span>订单工序总数</span><b>{int(payload.get('task_count',0) or 0)}</b></div>
    <div class="metric"><span>待生产</span><b>{int(payload.get('pending_count',0) or 0)}</b></div>
    <div class="metric"><span>生产中</span><b>{int(payload.get('in_progress_count',0) or 0)}</b></div>
    <div class="metric"><span>已完成</span><b>{int(payload.get('completed_count',0) or 0)}</b></div>
    <div class="metric"><span>延期 / 重要</span><b>{int(payload.get('overdue_count',0) or 0)} / {int(payload.get('important_count',0) or 0)}</b></div></div></section>
    <section class="section"><div class="section-title">🔎 订单工序明细</div><table><thead><tr><th>产品订单号</th><th>产品名称</th><th>工序</th><th>状态</th><th>总米数</th><th>客户等级</th><th>计划完成时间</th><th>交货日期</th><th>优先级</th></tr></thead><tbody>{body}</tbody></table></section>
    <footer>车间智能体 · 数据来自经过校验的单部门模拟数据</footer></main></body></html>"""


def build_work_report_html(payload: dict[str, Any]) -> str:
    source_rows = "".join(
        "<tr>"
        f"<td>{_text(row.get('form_name'))}</td>"
        f"<td>{int(row.get('raw_record_count',0) or 0)}</td>"
        f"<td>{int(row.get('excluded_quality_inspection_record_count',0) or 0)}</td>"
        f"<td>{int(row.get('included_record_count',0) or 0)}</td></tr>"
        for row in payload.get("source_record_breakdown", [])
    ) or '<tr><td class="empty" colspan="4">暂无报工来源明细</td></tr>'
    performers = "".join(
        "<tr>"
        f"<td>{index}</td><td>{_text(row.get('reporter_name'))}</td>"
        f"<td>{float(row.get('completed_centimeters',0) or 0):.2f} 公分</td>"
        f"<td>{_percent(row.get('completion_rate'))}</td><td>{int(row.get('report_count',0) or 0)}</td></tr>"
        for index, row in enumerate(payload.get("performers", []), start=1)
    ) or '<tr><td class="empty" colspan="5">昨日暂无有效报工人员数据</td></tr>'
    details = "".join(
        "<tr>"
        f"<td>{_text(row.get('reported_at'))}</td><td>{_text(row.get('product_order_no'))}</td>"
        f"<td>{_text(row.get('process_name'))}</td><td>{_text(row.get('reporter_name'))}</td>"
        f"<td>{_text(row.get('completed_quantity'))} {_text(row.get('quantity_unit'))}</td>"
        f"<td>{_percent(row.get('completion_rate'))}</td>"
        f"<td class={'good' if row.get('matched') else 'danger'}>{'已匹配' if row.get('matched') else '待核对'}</td>"
        f"<td>{_text(row.get('remark'))}</td></tr>"
        for row in payload.get("rows", [])
    ) or '<tr><td class="empty" colspan="8">昨日暂无报工明细</td></tr>'
    style = _base_style() + ".work-metrics{grid-template-columns:repeat(4,1fr)}"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>{style}</style></head><body><main>
    <h1>车间报工日报</h1><div class="meta">统计日期：{_text(payload.get('report_date'))} ｜ 部门：{_text(payload.get('department'))}</div>
    <div class="summary">📋 当前报工情况为 <strong>{_text(payload.get('health_status'))}</strong>。{_text(payload.get('health_summary'))}；
    有效报工记录 <b>{int(payload.get('report_record_count',0) or 0)}</b> 条，去重后参与统计 <b>{int(payload.get('deduplicated_report_record_count',0) or 0)}</b> 条；报工表实际订单工序 <b>{int(payload.get('reported_count',0) or 0)}</b>，匹配计划工序 <b>{int(payload.get('matched_reported_count',0) or 0)}</b> / 应报工订单工序 <b>{int(payload.get('expected_count',0) or 0)}</b>，报工率 <b>{_percent(payload.get('report_rate'))}</b>。</div>
    <section class="section"><div class="section-title">📊 报工概况</div><div class="metrics work-metrics">
    <div class="metric"><span>有效报工记录</span><b>{int(payload.get('report_record_count',0) or 0)}</b></div>
    <div class="metric"><span>应报工订单工序</span><b>{int(payload.get('expected_count',0) or 0)}</b></div>
    <div class="metric"><span>报工表实际订单工序</span><b>{int(payload.get('reported_count',0) or 0)}</b></div>
    <div class="metric"><span>匹配计划工序</span><b>{int(payload.get('matched_reported_count',0) or 0)}</b></div>
    <div class="metric"><span>未报工订单工序</span><b>{int(payload.get('pending_report_count',0) or 0)}</b></div>
    <div class="metric"><span>完成订单数</span><b>{int(payload.get('completed_order_count',0) or 0)}</b></div>
    <div class="metric"><span>昨日完成公分数</span><b>{float(payload.get('completed_centimeters',0) or 0):.2f} 公分</b></div></div></section>
    <section class="section"><div class="section-title">🧮 报工记录口径</div><table><thead><tr><th>数据表</th><th>原始记录</th><th>排除质检</th><th>有效报工</th></tr></thead><tbody>{source_rows}</tbody></table>
    <div class="summary">合计：{int(payload.get('report_record_count_before_exclusions',0) or 0)} - {int(payload.get('excluded_quality_inspection_record_count',0) or 0)} = <b>{int(payload.get('report_record_count',0) or 0)} 条有效报工记录</b></div></section>
    <section class="section"><div class="section-title">🏅 报工人员表现</div><table><thead><tr><th>排名</th><th>报工人员</th><th>完成公分数</th><th>平均完成率</th><th>报工条数</th></tr></thead><tbody>{performers}</tbody></table></section>
    <section class="section"><div class="section-title">🔎 报工明细</div><table><thead><tr><th>报工时间</th><th>产品订单号</th><th>工序</th><th>报工人员</th><th>完成量</th><th>完成率</th><th>基础任务</th><th>备注</th></tr></thead><tbody>{details}</tbody></table></section>
    <footer>车间智能体 · 焊接部合并两张报工表 · 排除质检工序 · 长度只读取总公分数字段</footer></main></body></html>"""
