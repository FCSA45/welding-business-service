"""Persistence for immutable, versioned workshop report snapshots."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import WorkshopYesterdayReportRow
from app.errors import AppError


class WorkshopYesterdayReportStore:
    """Persist immutable, versioned workshop report snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, payload: dict, *, source_type: str = "mock") -> tuple[WorkshopYesterdayReportRow, bool]:
        if not isinstance(payload, dict):
            raise AppError("WORKSHOP_REPORT_PAYLOAD_INVALID", "报告数据格式无效", status_code=422)
        raw_report_date = payload.get("report_date")
        if not isinstance(raw_report_date, str) or not raw_report_date.strip():
            raise AppError("WORKSHOP_REPORT_DATE_INVALID", "报告日期缺失或格式无效", status_code=422)
        try:
            report_date = date.fromisoformat(raw_report_date.strip())
        except (TypeError, ValueError) as exc:
            raise AppError("WORKSHOP_REPORT_DATE_INVALID", "报告日期格式无效", status_code=422) from exc
        if not isinstance(source_type, str) or not source_type.strip():
            raise AppError("WORKSHOP_REPORT_SOURCE_INVALID", "报告数据源无效", status_code=422)

        try:
            canonical = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        except (TypeError, ValueError, UnicodeError) as exc:
            raise AppError("WORKSHOP_REPORT_PAYLOAD_INVALID", "报告数据无法序列化", status_code=422) from exc

        try:
            existing = self.session.scalar(
                select(WorkshopYesterdayReportRow).where(
                    WorkshopYesterdayReportRow.report_date == report_date,
                    WorkshopYesterdayReportRow.content_hash == content_hash,
                )
            )
            if existing:
                return existing, False

            # Concurrency relies on the database UNIQUE(report_date, version)
            # constraint. Do not replace this with an application-only max()+1 check.
            version = int(
                self.session.scalar(
                    select(func.max(WorkshopYesterdayReportRow.version)).where(
                        WorkshopYesterdayReportRow.report_date == report_date
                    )
                )
                or 0
            ) + 1
            row = WorkshopYesterdayReportRow(
                report_date=report_date,
                version=version,
                content_hash=content_hash,
                payload_json=payload,
                source_type=source_type.strip(),
            )
            self.session.add(row)
            self.session.commit()
            self.session.refresh(row)
            return row, True
        except IntegrityError as exc:
            self.session.rollback()
            try:
                concurrent = self.session.scalar(
                    select(WorkshopYesterdayReportRow).where(
                        WorkshopYesterdayReportRow.report_date == report_date,
                        WorkshopYesterdayReportRow.content_hash == content_hash,
                    )
                )
            except SQLAlchemyError as query_exc:
                self.session.rollback()
                raise AppError(
                    "WORKSHOP_REPORT_DATABASE_ERROR",
                    "报告保存失败，请稍后重试",
                    status_code=503,
                ) from query_exc
            if concurrent:
                return concurrent, False
            raise AppError(
                "WORKSHOP_REPORT_VERSION_CONFLICT",
                "报告版本并发冲突，请稍后重试",
                status_code=409,
            ) from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise AppError(
                "WORKSHOP_REPORT_DATABASE_ERROR",
                "报告保存失败，请稍后重试",
                status_code=503,
            ) from exc
        except Exception as exc:
            self.session.rollback()
            raise AppError(
                "WORKSHOP_REPORT_SAVE_FAILED",
                "报告保存失败，请稍后重试",
                status_code=503,
            ) from exc
