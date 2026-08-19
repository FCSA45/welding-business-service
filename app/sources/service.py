from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel

from app.errors import AppError
from app.reports.models import SourceRecord, SyncRecord
from app.sources.base import DataSource, InvalidRow


class RecordListingRepository(Protocol):
    def list_all(self, source: str) -> list[SourceRecord]: ...


class OperationRecordRepository(Protocol):
    def insert_missing(self, records: list[SourceRecord]) -> tuple[int, int]: ...


class SyncRunRepository(Protocol):
    def create(self, **kwargs): ...


class SyncResult(BaseModel):
    source: str
    read_count: int
    valid_count: int
    inserted_count: int
    duplicate_count: int
    invalid_count: int
    invalid_rows: list[InvalidRow]
    records: list[SyncRecord]


class SyncService:
    def __init__(
        self,
        *,
        source_factory: Callable[[], DataSource],
        record_repository: OperationRecordRepository,
        run_repository: SyncRunRepository,
    ) -> None:
        self.source_factory = source_factory
        self.record_repository = record_repository
        self.run_repository = run_repository

    def sync(self) -> SyncResult:
        source = self.source_factory()
        try:
            batch = source.fetch_records()
        except AppError as exc:
            self.run_repository.create(
                source=getattr(source, "source_name", "unknown"),
                read_count=0,
                valid_count=0,
                inserted_count=0,
                duplicate_count=0,
                invalid_count=0,
                status="failed",
                error_code=exc.code,
            )
            raise
        inserted_count, duplicate_count = self.record_repository.insert_missing(
            batch.records
        )
        result = SyncResult(
            source=batch.source,
            read_count=batch.read_count,
            valid_count=len(batch.records),
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            invalid_count=len(batch.invalid_rows),
            invalid_rows=batch.invalid_rows,
            records=[
                SyncRecord(
                    report_date=record.report_date,
                    platform=record.platform,
                    account_name=record.account_name,
                    operator_name=record.operator_name,
                    published_count=record.published_count,
                    script_count=record.script_count,
                    filled_script_data_count=record.filled_script_data_count,
                    note=record.note,
                )
                for record in batch.records
            ],
        )
        self.run_repository.create(
            source=result.source,
            read_count=result.read_count,
            valid_count=result.valid_count,
            inserted_count=result.inserted_count,
            duplicate_count=result.duplicate_count,
            invalid_count=result.invalid_count,
            status="completed",
        )
        return result


class SyncRecordService:
    def __init__(self, record_listing_repository: RecordListingRepository) -> None:
        self.record_listing_repository = record_listing_repository

    def get_all_records(self, source: str) -> list[SyncRecord]:
        source_records = self.record_listing_repository.list_all(source)
        return [
            SyncRecord(
                report_date=record.report_date,
                platform=record.platform,
                account_name=record.account_name,
                operator_name=record.operator_name,
                published_count=record.published_count,
                script_count=record.script_count,
                filled_script_data_count=record.filled_script_data_count,
                note=record.note,
            )
            for record in source_records
        ]
