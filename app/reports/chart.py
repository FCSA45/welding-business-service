from datetime import date
from html import escape
from pathlib import Path

from app.reports.models import SourceRecord


def build_operations_chart_svg(report_date: date, records: list[SourceRecord]) -> str:
    width, height = 960, 560
    left, bottom, chart_width, chart_height = 90, 450, 790, 320
    max_value = max([record.published_count for record in records] + [1])
    bar_width = max(40, min(100, chart_width // max(len(records), 1) - 14))
    bars: list[str] = []
    for index, record in enumerate(records):
        x = left + index * (chart_width // max(len(records), 1)) + 12
        bar_height = round(record.published_count / max_value * chart_height)
        y = bottom - bar_height
        label = escape(record.operator_name[:8])
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" rx="6" fill="#2f6fe4" />'
            f'<text x="{x + bar_width / 2}" y="{y - 12}" text-anchor="middle" class="value">{record.published_count}</text>'
            f'<text x="{x + bar_width / 2}" y="{bottom + 28}" text-anchor="middle" class="label">{label}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#ffffff"/>
<style>text{{font-family:Arial,"Microsoft YaHei",sans-serif}}.title{{font-size:24px;font-weight:700;fill:#273343}}.sub{{font-size:14px;fill:#687587}}.axis{{stroke:#dfe5ed;stroke-width:1}}.value{{font-size:14px;font-weight:700;fill:#273343}}.label{{font-size:13px;fill:#566373}}</style>
<text x="40" y="52" class="title">运营发布数量</text>
<g transform="translate(875 28)" fill="none" stroke="#2f6fe4" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 42V8M4 42H42"/><path d="M12 32l8-9 7 5 13-17"/></g>
<text x="40" y="80" class="sub">广告牌标识业务 · {escape(report_date.isoformat())}</text>
<line x1="{left}" y1="{bottom}" x2="{left + chart_width}" y2="{bottom}" class="axis"/>
<line x1="{left}" y1="{bottom - chart_height}" x2="{left}" y2="{bottom}" class="axis"/>
{''.join(bars)}
</svg>'''


def save_operations_chart(directory: str | Path, report_date: date, records: list[SourceRecord]) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"operation-report-{report_date.isoformat()}.svg"
    path.write_text(build_operations_chart_svg(report_date, records), encoding="utf-8")
    return path
