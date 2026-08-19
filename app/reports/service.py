from collections import defaultdict
from datetime import date
from typing import Protocol
from uuid import uuid4

from app.reports.models import (
    OperatorSummary,
    ReportRequest,
    ReportResult,
    SourceRecord,
)
from app.reports.periods import resolve_period


class ReportRecordRepository(Protocol):
    def list_records(
        self,
        start_date: date,
        end_date: date,
        operator_name: str | None,
    ) -> list[SourceRecord]: ...


class ReportService:
    def __init__(self, repository: ReportRecordRepository) -> None:
        self.repository = repository

    def generate(self, request: ReportRequest) -> ReportResult:
        period_start, period_end = resolve_period(request.period, request.anchor_date)
        records = self.repository.list_records(
            period_start, period_end, request.operator_name
        )
        grouped: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for record in records:
            grouped[record.operator_name][0] += record.published_count
            grouped[record.operator_name][1] += record.script_count

        operators = [
            OperatorSummary(
                name=name,
                published_count=values[0],
                script_count=values[1],
            )
            for name, values in sorted(grouped.items())
        ]
        published_total = sum(item.published_count for item in operators)
        script_total = sum(item.script_count for item in operators)
        has_data = bool(records)
        status = "ok" if has_data else "no_data"
        error_code = None if has_data else "NO_DATA"
        if has_data:
            summary = (
                f"{period_start} 至 {period_end} 共 {len(operators)} 人提交 {len(records)} 条记录，"
                f"发布 {published_total} 条，脚本 {script_total} 个。"
            )
        else:
            summary = f"{period_start} 至 {period_end} 无有效运营数据。"

        return ReportResult(
            request_id=f"req_{uuid4().hex[:12]}",
            status=status,
            error_code=error_code,
            period=request.period,
            period_start=period_start,
            period_end=period_end,
            record_count=len(records),
            operator_count=len(operators),
            published_total=published_total,
            script_total=script_total,
            operators=operators,
            summary=summary,
        )

