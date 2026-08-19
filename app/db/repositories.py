from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.daily_reports.models import DailyReportUpsertRequest
from app.db.models import (
    DailyReportRow,
    OperationDailyReportRow,
    OperationRecordRow,
    PerformanceDailyAggregateRow,
    PerformanceReportSnapshotRow,
    ScheduledDeliveryRow,
    SyncRunRow,
)
from app.operation_reports.models import OperationDailyReportUpsertRequest, OperationPublicationCountRequest
from app.reports.models import SourceRecord


class SqlAlchemyReportRecordRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[SourceRecord]:
        rows = self.session.scalars(
            select(OperationRecordRow).order_by(OperationRecordRow.report_date, OperationRecordRow.operator_name)
        ).all()
        return [
            SourceRecord(
                report_date=row.report_date,
                platform=row.platform,
                account_name=row.account_name,
                operator_name=row.operator_name,
                published_count=row.published_count,
                script_count=row.script_count,
                filled_script_data_count=row.filled_script_data_count,
                note=row.note,
                source=row.source,
                source_row_id=row.source_row_id,
            )
            for row in rows
        ]

    def list_records(
        self,
        start_date: date,
        end_date: date,
        operator_name: str | None,
    ) -> list[SourceRecord]:
        statement = select(OperationRecordRow).where(
            OperationRecordRow.report_date.between(start_date, end_date)
        )
        if operator_name is not None:
            statement = statement.where(OperationRecordRow.operator_name == operator_name)
        rows = self.session.scalars(
            statement.order_by(OperationRecordRow.operator_name, OperationRecordRow.id)
        ).all()
        return [
            SourceRecord(
                report_date=row.report_date,
                platform=row.platform,
                account_name=row.account_name,
                operator_name=row.operator_name,
                published_count=row.published_count,
                script_count=row.script_count,
                filled_script_data_count=row.filled_script_data_count,
                note=row.note,
                source=row.source,
                source_row_id=row.source_row_id,
            )
            for row in rows
        ]

    def list_all(self, source: str) -> list[SourceRecord]:
        statement = select(OperationRecordRow).where(
            OperationRecordRow.source == source
        )
        rows = self.session.scalars(
            statement.order_by(
                OperationRecordRow.report_date,
                OperationRecordRow.operator_name,
                OperationRecordRow.id,
            )
        ).all()
        return [
            SourceRecord(
                report_date=row.report_date,
                platform=row.platform,
                account_name=row.account_name,
                operator_name=row.operator_name,
                published_count=row.published_count,
                script_count=row.script_count,
                filled_script_data_count=row.filled_script_data_count,
                note=row.note,
                source=row.source,
                source_row_id=row.source_row_id,
            )
            for row in rows
        ]


class SqlAlchemyOperationRecordRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_missing(self, records: list[SourceRecord]) -> tuple[int, int]:
        if not records:
            return 0, 0
        values = [
            {
                "source": record.source,
                "source_row_id": record.source_row_id,
                "source_hash": record.source_hash,
                "report_date": record.report_date,
                "platform": record.platform,
                "account_name": record.account_name,
                "operator_name": record.operator_name,
                "published_count": record.published_count,
                "script_count": record.script_count,
                "filled_script_data_count": record.filled_script_data_count,
                "note": record.note,
            }
            for record in records
        ]
        statement = insert(OperationRecordRow).values(values)
        statement = statement.on_conflict_do_nothing(
            index_elements=[OperationRecordRow.source_hash]
        ).returning(OperationRecordRow.id)
        result = self.session.execute(statement)
        inserted = len(result.scalars().all())
        return inserted, len(records) - inserted

    def upsert_test_record(self, request: OperationPublicationCountRequest) -> tuple[OperationRecordRow, bool]:
        source = "mock_api"
        source_row_id = request.source_row_id or f"{request.report_date}:{request.operator_name}"
        source_hash = __import__("hashlib").sha256(
            f"{source}|{source_row_id}|{request.report_date}|{request.platform}|{request.account_name}|"
            f"{request.operator_name}|{request.published_count}|{request.script_count}|"
            f"{request.filled_script_data_count}|{request.note}".encode("utf-8")
        ).hexdigest()
        row = self.session.scalar(
            select(OperationRecordRow).where(OperationRecordRow.source_hash == source_hash)
        )
        if row is not None:
            return row, True
        row = OperationRecordRow(
            source=source,
            source_row_id=source_row_id,
            source_hash=source_hash,
            report_date=request.report_date,
            platform=request.platform,
            account_name=request.account_name,
            operator_name=request.operator_name,
            published_count=request.published_count,
            script_count=request.script_count,
            filled_script_data_count=request.filled_script_data_count,
            note=request.note,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row, False


class SqlAlchemyOperationDailyReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_reports(self, start_date, end_date) -> list[OperationDailyReportRow]:
        statement = select(OperationDailyReportRow)
        if start_date is not None:
            statement = statement.where(OperationDailyReportRow.report_date >= start_date)
        if end_date is not None:
            statement = statement.where(OperationDailyReportRow.report_date <= end_date)
        return list(self.session.scalars(statement.order_by(OperationDailyReportRow.report_date.desc(), OperationDailyReportRow.id.desc())).all())

    def upsert(self, request: OperationDailyReportUpsertRequest, source_hash: str) -> OperationDailyReportRow:
        row = self.session.scalar(
            select(OperationDailyReportRow).where(OperationDailyReportRow.source_hash == source_hash)
        )
        values = request.model_dump()
        if row is None:
            row = OperationDailyReportRow(source_hash=source_hash, **values)
            self.session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(row)
        return row


class SqlAlchemyPerformanceCheckRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_publication_details(self, start_date: date, end_date: date):
        statement = select(OperationRecordRow).where(
            OperationRecordRow.report_date.between(start_date, end_date)
        )
        return list(self.session.scalars(statement.order_by(OperationRecordRow.report_date)).all())

    def list_official_summaries(self, start_date: date, end_date: date):
        statement = select(OperationDailyReportRow).where(
            OperationDailyReportRow.report_date.between(start_date, end_date)
        )
        return list(self.session.scalars(statement.order_by(OperationDailyReportRow.report_date)).all())


class SqlAlchemyPerformanceReportingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_daily(self, report_date: date, items: list) -> list[PerformanceDailyAggregateRow]:
        self.session.execute(
            delete(PerformanceDailyAggregateRow).where(
                PerformanceDailyAggregateRow.report_date == report_date
            )
        )
        rows = [
            PerformanceDailyAggregateRow(
                report_date=item.report_date,
                platform=item.platform,
                account_name=item.account_name,
                operator_name=item.operator_name,
                reported_published_count=item.reported_published_count,
                actual_published_count=item.actual_published_count,
                publication_difference=item.publication_difference,
                reported_script_count=item.reported_script_count,
                actual_script_count=item.actual_script_count,
                filled_script_data_count=item.filled_script_data_count,
                script_data_completeness_rate=item.script_data_completeness_rate,
                publication_agreement_rate=item.publication_agreement_rate,
                status=item.status,
            )
            for item in items
        ]
        self.session.add_all(rows)
        self.session.commit()
        return rows

    def list_daily(self, start_date: date, end_date: date) -> list[PerformanceDailyAggregateRow]:
        statement = select(PerformanceDailyAggregateRow).where(
            PerformanceDailyAggregateRow.report_date.between(start_date, end_date)
        )
        return list(self.session.scalars(statement.order_by(
            PerformanceDailyAggregateRow.report_date,
            PerformanceDailyAggregateRow.platform,
            PerformanceDailyAggregateRow.account_name,
        )).all())

    def create_snapshot(self, period_start: date, period_end: date, payload: dict) -> PerformanceReportSnapshotRow:
        latest_version = self.session.scalar(
            select(func.max(PerformanceReportSnapshotRow.version)).where(
                PerformanceReportSnapshotRow.period_type == "weekly",
                PerformanceReportSnapshotRow.period_start == period_start,
                PerformanceReportSnapshotRow.period_end == period_end,
            )
        ) or 0
        row = PerformanceReportSnapshotRow(
            period_type="weekly",
            period_start=period_start,
            period_end=period_end,
            version=latest_version + 1,
            status="ready",
            payload_json=payload,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def get_snapshot(self, snapshot_id: int) -> PerformanceReportSnapshotRow | None:
        return self.session.get(PerformanceReportSnapshotRow, snapshot_id)

    def list_snapshots(self, limit: int = 20) -> list[PerformanceReportSnapshotRow]:
        statement = select(PerformanceReportSnapshotRow).where(
            PerformanceReportSnapshotRow.period_type == "weekly"
        ).order_by(PerformanceReportSnapshotRow.generated_at.desc()).limit(limit)
        return list(self.session.scalars(statement).all())


class SqlAlchemySyncRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        source: str,
        read_count: int,
        valid_count: int,
        inserted_count: int,
        duplicate_count: int,
        invalid_count: int,
        status: str,
        error_code: str | None = None,
    ) -> SyncRunRow:
        run = SyncRunRow(
            source=source,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            status=status,
            read_count=read_count,
            valid_count=valid_count,
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            invalid_count=invalid_count,
            error_code=error_code,
        )
        self.session.add(run)
        self.session.commit()
        return run


class SqlAlchemyDailyReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_reports(
        self,
        start_date: date | None,
        end_date: date | None,
    ) -> list[DailyReportRow]:
        statement = select(DailyReportRow)
        if start_date is not None:
            statement = statement.where(DailyReportRow.report_date >= start_date)
        if end_date is not None:
            statement = statement.where(DailyReportRow.report_date <= end_date)
        return list(
            self.session.scalars(
                statement.order_by(
                    DailyReportRow.report_date.desc(),
                    DailyReportRow.submitted_at.desc(),
                )
            ).all()
        )

    def upsert(self, request: DailyReportUpsertRequest) -> DailyReportRow:
        row = self.session.scalar(
            select(DailyReportRow).where(
                DailyReportRow.employee_open_id == request.employee_open_id,
                DailyReportRow.report_date == request.report_date,
            )
        )
        submitted_at = request.submitted_at or datetime.now(timezone.utc)
        if row is None:
            row = DailyReportRow(
                report_date=request.report_date,
                employee_open_id=request.employee_open_id,
                employee_name=request.employee_name,
                completed_work=request.completed_work,
                completed_count=request.completed_count,
                next_plan=request.next_plan,
                issues=request.issues,
                submitted_at=submitted_at,
                updated_at=submitted_at,
                version=1,
                status=request.status.value,
                source=request.source,
                source_message_id=request.source_message_id,
            )
            self.session.add(row)
        else:
            row.employee_name = request.employee_name
            row.completed_work = request.completed_work
            row.completed_count = request.completed_count
            row.next_plan = request.next_plan
            row.issues = request.issues
            row.submitted_at = submitted_at
            row.updated_at = datetime.now(timezone.utc)
            row.version += 1
            row.status = request.status.value
            row.source = request.source
            row.source_message_id = request.source_message_id
        self.session.commit()
        self.session.refresh(row)
        return row


class SqlAlchemyScheduledDeliveryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def already_sent(self, delivery_type: str, delivery_date: date) -> bool:
        return self.session.scalar(
            select(ScheduledDeliveryRow.id).where(
                ScheduledDeliveryRow.delivery_type == delivery_type,
                ScheduledDeliveryRow.delivery_date == delivery_date,
            )
        ) is not None

    def record_sent(self, delivery_type: str, delivery_date: date, chat_id: str) -> None:
        self.session.add(
            ScheduledDeliveryRow(
                delivery_type=delivery_type,
                delivery_date=delivery_date,
                chat_id=chat_id,
                sent_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()
