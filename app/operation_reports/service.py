import hashlib
import json
from datetime import date, datetime, timezone
from typing import Protocol

from app.db.models import OperationRecordRow
from app.daily_reports.models import DailyReportUpsertRequest
from app.daily_reports.service import DailyReportService
from app.operation_reports.models import (
    OperationDailyReportRecord,
    OperationDailyReportUpsertRequest,
    OperationPublicationCountRequest,
    OperationPublicationCountResponse,
)


class OperationDailyReportRepository(Protocol):
    def list_reports(self, start_date: date | None, end_date: date | None): ...
    def upsert(self, request: OperationDailyReportUpsertRequest, source_hash: str): ...


class OperationRecordRepository(Protocol):
    def upsert_test_record(self, request: OperationPublicationCountRequest) -> tuple[OperationRecordRow, bool]: ...


def operation_hash(request: OperationDailyReportUpsertRequest) -> str:
    payload = request.model_dump(mode="json")
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class OperationDailyReportService:
    def __init__(self, repository: OperationDailyReportRepository) -> None:
        self.repository = repository

    def list_reports(self, start_date: date | None = None, end_date: date | None = None) -> list[OperationDailyReportRecord]:
        return [self._to_record(row) for row in self.repository.list_reports(start_date, end_date)]

    def upsert(self, request: OperationDailyReportUpsertRequest) -> OperationDailyReportRecord:
        return self._to_record(self.repository.upsert(request, operation_hash(request)))

    @staticmethod
    def _to_record(row) -> OperationDailyReportRecord:
        return OperationDailyReportRecord(
            id=row.id,
            report_date=row.report_date,
            platform=row.platform,
            account_name=row.account_name,
            operator_name=row.operator_name,
            project_name=row.project_name,
            published_count=row.published_count,
            submitted_script_count=row.submitted_script_count,
            script_data_filled_count=row.script_data_filled_count,
            completed_work=row.completed_work,
            next_plan=row.next_plan,
            issues=row.issues,
            source=row.source,
            source_row_id=row.source_row_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class LegacyOperationDailyReportService:
    """Keep the operation-report API backed by the canonical daily_reports table."""

    def __init__(self, service: DailyReportService) -> None:
        self.service = service

    def list_reports(self, start_date=None, end_date=None):
        return [self._to_operation_record(row) for row in self.service.list_reports(start_date, end_date)]

    def upsert(self, request: OperationDailyReportUpsertRequest):
        row = self.service.submit(
            DailyReportUpsertRequest(
                report_date=request.report_date,
                employee_open_id=f"operator:{request.operator_name}",
                employee_name=request.operator_name,
                completed_work=request.completed_work or request.project_name or "运营日报",
                completed_count=request.published_count,
                next_plan=request.next_plan,
                issues=request.issues,
                source=request.source,
                source_message_id=request.source_row_id,
            )
        )
        return self._to_operation_record(row)

    @staticmethod
    def _to_operation_record(row):
        return OperationDailyReportRecord(
            id=row.id,
            report_date=row.report_date,
            platform=getattr(row, "platform", "未指定平台"),
            account_name=getattr(row, "account_name", "未指定账号"),
            operator_name=row.employee_name,
            project_name="",
            published_count=row.completed_count,
            submitted_script_count=0,
            script_data_filled_count=0,
            completed_work=row.completed_work,
            next_plan=row.next_plan,
            issues=row.issues,
            source=row.source,
            source_row_id=None,
            created_at=row.submitted_at,
            updated_at=row.updated_at,
        )


class OperationPublicationCountService:
    def __init__(self, repository: OperationRecordRepository) -> None:
        self.repository = repository

    def submit(self, request: OperationPublicationCountRequest) -> OperationPublicationCountResponse:
        row, duplicate = self.repository.upsert_test_record(request)
        return OperationPublicationCountResponse(
            id=row.id,
            report_date=row.report_date,
            platform=row.platform,
            account_name=row.account_name,
            operator_name=row.operator_name,
            published_count=row.published_count,
            script_count=row.script_count,
            filled_script_data_count=row.filled_script_data_count,
            note=row.note,
            source=row.source,
            duplicate=duplicate,
        )
