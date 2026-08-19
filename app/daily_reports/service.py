from datetime import date, datetime, timezone
from typing import Protocol

from app.daily_reports.models import DailyReportRecord, DailyReportUpsertRequest
from app.db.models import DailyReportRow


class DailyReportRepository(Protocol):
    def list_reports(
        self,
        start_date: date | None,
        end_date: date | None,
    ) -> list[DailyReportRow]: ...

    def upsert(self, request: DailyReportUpsertRequest) -> DailyReportRow: ...


class DailyReportService:
    def __init__(self, repository: DailyReportRepository) -> None:
        self.repository = repository

    def list_reports(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyReportRecord]:
        return [self._to_record(row) for row in self.repository.list_reports(start_date, end_date)]

    def submit(self, request: DailyReportUpsertRequest) -> DailyReportRecord:
        if request.submitted_at is None:
            request = request.model_copy(update={"submitted_at": datetime.now(timezone.utc)})
        return self._to_record(self.repository.upsert(request))

    @staticmethod
    def _to_record(row: DailyReportRow) -> DailyReportRecord:
        return DailyReportRecord(
            id=row.id,
            report_date=row.report_date,
            employee_open_id=row.employee_open_id,
            employee_name=row.employee_name,
            completed_work=row.completed_work,
            completed_count=row.completed_count,
            next_plan=row.next_plan,
            issues=row.issues,
            submitted_at=row.submitted_at,
            updated_at=row.updated_at,
            version=row.version,
            status=row.status,
            source=row.source,
        )

