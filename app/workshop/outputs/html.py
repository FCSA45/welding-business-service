from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def _rate(value: float | None) -> str:
    return "暂无" if value is None else f"{value:.1%}"


def _rows(items: list[dict[str, Any]], *, important: bool = False, limit: int = 3) -> str:
    rows = []
    for row in items[:limit]:
        note = row.get("important_reason") if important else row.get("incomplete_processes")
        grade = escape(str(row.get("customer_grade") or "-"))
        priority = escape(str(row.get("priority") or ("重要订单" if important else "延期订单")))
        rows.append(
            f"<tr><td><b>{escape(str(row['product_order_no']))}</b></td>"
            f"<td><span class='grade g-{grade.lower()}'>{grade}</span></td>"
            f"<td>{'已完工' if row['complete'] else '待完工'}</td>"
            f"<td class='num'>{float(row['centimeters']):.0f}</td>"
            f"<td>{escape(str(row.get('incomplete_processes') or '-'))}</td>"
            f"<td><span class='priority'>{priority}</span><small>{escape(str(note or '-'))}</small></td></tr>"
        )
    return "".join(rows) or "<tr><td colspan='6' class='empty'>暂无相关订单</td></tr>"


def render_department_report_html(payload: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    limit = int(payload.get("example_limit", 3))
    delayed_examples = payload.get("delayed_example_orders", payload["delayed_open_orders"][:limit])
    important_examples = payload.get("important_example_orders", payload["important_orders"][:limit])
    delayed = _rows(delayed_examples, limit=limit)
    important = _rows(important_examples, important=True, limit=limit)
    recommendations = payload.get("priority_recommendations", [])[:10]
    recommendation_rows = "".join(
        f"<tr><td class='num'>{index}</td><td><b>{escape(str(row.get('product_order_no') or '-'))}</b></td>"
        f"<td><span class='priority'>{escape(str(row.get('priority') or '-'))}</span></td>"
        f"<td>{escape(str(row.get('incomplete_processes') or '-'))}</td>"
        f"<td>{escape(str(row.get('recommendation') or '-'))}</td></tr>"
        for index, row in enumerate(recommendations, start=1)
    ) or "<tr><td colspan='5' class='empty'>当前没有需要额外安排的未完工订单</td></tr>"
    generated = escape(payload["generated_at"].replace("T", " "))
    html = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><style>
*{{box-sizing:border-box}}body{{margin:0;background:#edf2f7;color:#1d2b3a;font-family:'Microsoft YaHei','Segoe UI',sans-serif}}main{{width:1200px;margin:auto;background:#fff;min-height:100vh;padding-bottom:30px}}header{{padding:28px 34px;color:#fff;background:linear-gradient(135deg,#0b2742,#145a73)}}h1{{margin:0 0 8px;font-size:30px;letter-spacing:1px}}header p{{margin:0;color:#d8e8ee;font-size:14px}}section{{margin:22px 34px}}h2{{font-size:20px;color:#123f69;border-left:5px solid #f08a24;padding-left:11px;margin:0 0 12px}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}.card{{padding:17px 18px;background:#f7fafc;border:1px solid #d9e4ec;border-radius:8px}}.card span{{display:block;color:#617286;font-size:13px}}.card b{{display:block;margin-top:8px;font-size:27px;color:#0c3863}}.rates{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.rate{{border:1px solid #d3dfe8;border-radius:8px;overflow:hidden}}.rate h3{{margin:0;padding:11px 16px;color:#fff;background:#17617a;font-size:16px}}.rate div{{display:grid;grid-template-columns:repeat(3,1fr);text-align:center;padding:15px;font-size:16px}}table{{width:100%;border-collapse:separate;border-spacing:0;border:1px solid #d6e0e8;border-radius:8px;overflow:hidden;font-size:13px}}th{{background:#123f69;color:#fff;font-weight:600;padding:12px 10px;text-align:left}}td{{padding:11px 10px;border-top:1px solid #e4ebf0;vertical-align:top}}tbody tr:nth-child(even){{background:#f8fafc}}td.num{{text-align:right;font-variant-numeric:tabular-nums}}td small{{display:block;color:#718096;margin-top:4px;line-height:1.45}}.grade,.priority{{display:inline-block;padding:3px 9px;border-radius:12px;font-weight:700;white-space:nowrap}}.priority{{background:#fff0d5;color:#9b5a00}}.g-a{{background:#e85b5b;color:#fff}}.g-b{{background:#f3a35c}}.g-c{{background:#f6d35d}}.g-d{{background:#91bce3}}.g-e{{background:#dce4ef}}.empty{{text-align:center;color:#718096;padding:24px}}.advice{{background:#fff8eb;border:1px solid #f2d39b;border-radius:8px;padding:14px 16px}}footer{{margin:22px 34px 0;padding:14px;background:#f2f5f8;color:#607286;border-radius:6px;font-size:12px;line-height:1.6}}
</style></head><body><main><header><h1>{escape(payload['department'])}｜昨日订单日报</h1><p>统计日期：{payload['yesterday_date']}　生成时间：{generated}</p></header>
<section class='cards'><div class='card'><span>订单总数</span><b>{payload['yesterday_plan_order_count']}</b></div><div class='card'><span>计划总公分</span><b>{payload['yesterday_plan_cm']:.0f}</b></div><div class='card'><span>已完工公分</span><b>{payload['completed_cm']:.0f}</b></div><div class='card'><span>公分完成率</span><b>{_rate(payload['completion_rate'])}</b></div></section>
<section class='rates'><div class='rate'><h3>延期订单完成率</h3><div><span>完成 {payload['delayed_completed_count']}</span><span>总数 {payload['delayed_order_count']}</span><b>{_rate(payload['delayed_completion_rate'])}</b></div></div><div class='rate'><h3>常规订单完成率</h3><div><span>完成 {payload['regular_completed_count']}</span><span>总数 {payload['regular_order_count']}</span><b>{_rate(payload['regular_completion_rate'])}</b></div></div></section>
<section><h2>待完工延期订单（共 {payload['delayed_open_order_count']} 单，展示 {limit} 单）</h2><table><thead><tr><th>订单号</th><th>等级</th><th>状态</th><th>总公分</th><th>未完成工序</th><th>优先级说明</th></tr></thead><tbody>{delayed}</tbody></table></section>
<section><h2>重要订单（共 {len(payload['important_orders'])} 单，展示 {limit} 单）</h2><table><thead><tr><th>订单号</th><th>等级</th><th>状态</th><th>总公分</th><th>未完成工序</th><th>优先级说明</th></tr></thead><tbody>{important}</tbody></table></section>
<section><h2>建议优先处理</h2><div class='advice'><table><thead><tr><th>顺序</th><th>订单号</th><th>优先级</th><th>未完成工序</th><th>建议</th></tr></thead><tbody>{recommendation_rows}</tbody></table></div></section>
<footer>统计口径：按计划完成日期及所选部门筛选；订单数和公分数均按订单编号去重，同一订单的多个工序或领料记录只计算一次。建议仅供生产安排参考，不会自动修改订单。</footer></main></body></html>"""
    path.write_text(html, encoding="utf-8")
    return path
