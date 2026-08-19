from collections import defaultdict
from datetime import date
from typing import Protocol

from app.performance_checks.models import (
    PerformanceCheckItem,
    PerformanceCheckRequest,
    PerformanceCheckResult,
)
from app.reports.periods import resolve_period


MatchKey = tuple[date, str, str, str]


class PerformanceCheckRepository(Protocol):
    def list_publication_details(self, start_date: date, end_date: date): ...
    def list_official_summaries(self, start_date: date, end_date: date): ...


class PerformanceCheckService:
    def __init__(self, repository: PerformanceCheckRepository) -> None:
        self.repository = repository

    def generate(self, request: PerformanceCheckRequest) -> PerformanceCheckResult:
        period_start, period_end = resolve_period(request.period, request.anchor_date)
        actual = self._group_actual(self.repository.list_publication_details(period_start, period_end))
        reported = self._group_reported(self.repository.list_official_summaries(period_start, period_end))
        keys = sorted(set(actual) | set(reported))
        if request.operator_name:
            keys = [key for key in keys if key[3] == request.operator_name.strip()]

        items = [self._build_item(key, reported.get(key), actual.get(key)) for key in keys]
        matched_count = sum(item.status == "matched" for item in items)
        reported_total = sum(item.reported_published_count for item in items)
        actual_total = sum(item.actual_published_count for item in items)
        review_count = len(items) - matched_count
        summary = (
            f"{period_start} 至 {period_end} 共核查 {len(items)} 条账号绩效记录，"
            f"{matched_count} 条一致，{review_count} 条需要核查；"
            f"运营日报发布 {reported_total} 条，平台实际发布 {actual_total} 条。"
        )
        return PerformanceCheckResult(
            period=request.period,
            period_start=period_start,
            period_end=period_end,
            row_count=len(items),
            matched_count=matched_count,
            review_count=review_count,
            reported_published_total=reported_total,
            actual_published_total=actual_total,
            items=items,
            summary=summary,
        )

    @staticmethod
    def _key(row) -> MatchKey:
        return row.report_date, row.platform, row.account_name, row.operator_name

    def _group_actual(self, rows) -> dict[MatchKey, list[int]]:
        grouped: dict[MatchKey, list[int]] = defaultdict(lambda: [0, 0, 0])
        for row in rows:
            values = grouped[self._key(row)]
            values[0] += row.published_count
            values[1] += row.script_count
            values[2] += row.filled_script_data_count
        return grouped

    def _group_reported(self, rows) -> dict[MatchKey, list[int]]:
        grouped: dict[MatchKey, list[int]] = defaultdict(lambda: [0, 0, 0])
        for row in rows:
            values = grouped[self._key(row)]
            values[0] += row.published_count
            values[1] += row.submitted_script_count
            values[2] += row.script_data_filled_count
        return grouped

    @staticmethod
    def _build_item(key: MatchKey, reported: list[int] | None, actual: list[int] | None) -> PerformanceCheckItem:
        report_values = reported or [0, 0, 0]
        actual_values = actual or [0, 0, 0]
        if reported is None:
            status = "missing_report"
        elif actual is None:
            status = "missing_platform"
        # Business 1 compares only published counts; script counts belong to business 2.
        elif report_values[0] == actual_values[0]:
            status = "matched"
        else:
            status = "mismatch"

        reported_published, reported_scripts, reported_filled = report_values
        actual_published, actual_scripts, actual_filled = actual_values
        script_base = actual_scripts or reported_scripts
        filled_count = actual_filled or reported_filled
        completeness = 100.0 if script_base == 0 else min(filled_count / script_base * 100, 100.0)
        high = max(reported_published, actual_published)
        agreement = 100.0 if high == 0 else min(reported_published, actual_published) / high * 100
        return PerformanceCheckItem(
            report_date=key[0],
            platform=key[1],
            account_name=key[2],
            operator_name=key[3],
            reported_published_count=reported_published,
            actual_published_count=actual_published,
            publication_difference=reported_published - actual_published,
            reported_script_count=reported_scripts,
            actual_script_count=actual_scripts,
            filled_script_data_count=filled_count,
            script_data_completeness_rate=round(completeness, 1),
            publication_agreement_rate=round(agreement, 1),
            status=status,
        )
