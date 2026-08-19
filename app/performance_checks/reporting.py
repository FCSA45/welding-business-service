from collections import defaultdict
from datetime import date, timedelta
from typing import Protocol

from app.performance_checks.models import (
    DailyAggregateResult,
    PerformanceCheckRequest,
    WeeklySnapshotRecord,
)
from app.performance_checks.service import PerformanceCheckService
from app.reports.models import ReportPeriod
from app.reports.periods import resolve_period


class ReportingRepository(Protocol):
    def replace_daily(self, report_date: date, items: list): ...
    def list_daily(self, start_date: date, end_date: date): ...
    def create_snapshot(self, period_start: date, period_end: date, payload: dict): ...
    def get_snapshot(self, snapshot_id: int): ...
    def list_snapshots(self, limit: int = 20): ...


class PerformanceReportingService:
    def __init__(
        self,
        check_service: PerformanceCheckService,
        repository: ReportingRepository,
    ) -> None:
        self.check_service = check_service
        self.repository = repository

    def rebuild_daily(self, report_date: date) -> DailyAggregateResult:
        result = self.check_service.generate(
            PerformanceCheckRequest(period=ReportPeriod.DAILY, anchor_date=report_date)
        )
        self.repository.replace_daily(report_date, result.items)
        return DailyAggregateResult(
            report_date=report_date,
            row_count=result.row_count,
            matched_count=result.matched_count,
            review_count=result.review_count,
        )

    def generate_weekly(self, anchor_date: date) -> WeeklySnapshotRecord:
        period_start, period_end = resolve_period(ReportPeriod.WEEKLY, anchor_date)
        previous_start = period_start - timedelta(days=7)
        for offset in range(14):
            self.rebuild_daily(previous_start + timedelta(days=offset))

        current_rows = self.repository.list_daily(period_start, period_end)
        previous_rows = self.repository.list_daily(previous_start, period_start - timedelta(days=1))
        payload = self._build_week_payload(period_start, period_end, current_rows, previous_rows)
        return self._to_snapshot(
            self.repository.create_snapshot(period_start, period_end, payload)
        )

    def get_snapshot(self, snapshot_id: int) -> WeeklySnapshotRecord | None:
        row = self.repository.get_snapshot(snapshot_id)
        return self._to_snapshot(row) if row is not None else None

    def list_snapshots(self, limit: int = 20) -> list[WeeklySnapshotRecord]:
        return [self._to_snapshot(row) for row in self.repository.list_snapshots(limit)]

    @staticmethod
    def _metrics(rows) -> dict:
        reported = sum(row.reported_published_count for row in rows)
        actual = sum(row.actual_published_count for row in rows)
        reported_scripts = sum(row.reported_script_count for row in rows)
        actual_scripts = sum(row.actual_script_count for row in rows)
        filled = sum(row.filled_script_data_count for row in rows)
        script_base = sum(
            row.actual_script_count or row.reported_script_count for row in rows
        )
        high = max(reported, actual)
        return {
            "reported_published": reported,
            "actual_published": actual,
            "publication_difference": reported - actual,
            "publication_agreement_rate": round(100 if high == 0 else min(reported, actual) / high * 100, 1),
            "reported_scripts": reported_scripts,
            "actual_scripts": actual_scripts,
            "filled_script_data": filled,
            "script_completeness_rate": round(100 if script_base == 0 else min(filled / script_base * 100, 100), 1),
            "matched_count": sum(row.status == "matched" for row in rows),
            "review_count": sum(row.status != "matched" for row in rows),
            "account_count": len({(row.platform, row.account_name) for row in rows}),
            "operator_count": len({row.operator_name for row in rows}),
        }

    @classmethod
    def _build_week_payload(cls, period_start: date, period_end: date, rows, previous_rows) -> dict:
        metrics = cls._metrics(rows)
        previous = cls._metrics(previous_rows)
        previous_actual = previous["actual_published"]
        week_over_week = None if previous_actual == 0 else round(
            (metrics["actual_published"] - previous_actual) / previous_actual * 100, 1
        )

        days = []
        for offset in range(7):
            current_date = period_start + timedelta(days=offset)
            day_rows = [row for row in rows if row.report_date == current_date]
            day_metrics = cls._metrics(day_rows)
            days.append({"date": current_date.isoformat(), **day_metrics})

        platform_rows: dict[str, list] = defaultdict(list)
        for row in rows:
            platform_rows[row.platform].append(row)
        platforms = [
            {"platform": platform, **cls._metrics(items)}
            for platform, items in sorted(platform_rows.items())
        ]

        operator_rows: dict[str, list] = defaultdict(list)
        for row in rows:
            operator_rows[row.operator_name].append(row)
        operators = sorted(
            ({"operator_name": name, **cls._metrics(items)} for name, items in operator_rows.items()),
            key=lambda item: (-item["review_count"], -abs(item["publication_difference"])),
        )

        anomalies = sorted(
            [
                {
                    "date": row.report_date.isoformat(),
                    "platform": row.platform,
                    "account_name": row.account_name,
                    "operator_name": row.operator_name,
                    "difference": row.publication_difference,
                    "status": row.status,
                }
                for row in rows if row.status != "matched"
            ],
            key=lambda item: -abs(item["difference"]),
        )[:10]

        return {
            "title": f"绩效核查周报 · {period_start.isoformat()} 至 {period_end.isoformat()}",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "metrics": metrics,
            "previous_week": previous,
            "week_over_week_actual_published": week_over_week,
            "daily_series": days,
            "platforms": platforms,
            "operators": operators,
            "top_anomalies": anomalies,
            "data_state": "complete" if metrics["review_count"] == 0 else "needs_review",
        }

    @staticmethod
    def _to_snapshot(row) -> WeeklySnapshotRecord:
        return WeeklySnapshotRecord(
            id=row.id,
            period_type=row.period_type,
            period_start=row.period_start,
            period_end=row.period_end,
            version=row.version,
            status=row.status,
            payload=row.payload_json,
            generated_at=row.generated_at,
        )
