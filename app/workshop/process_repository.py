"""Persistence for versioned workshop process records."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import WorkshopProcessRecordRow
from app.errors import AppError
from app.workshop.models import WorkshopProcessRecord


MAX_IMPORT_BATCH_SIZE = 1000


class WorkshopProcessImporter:
    """Save validated workshop records from mock or future ERP adapters."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def import_records(
        self,
        records: list[WorkshopProcessRecord],
        *,
        skip_invalid: bool = False,
    ) -> dict[str, int]:
        if not isinstance(records, list):
            raise AppError("WORKSHOP_PROCESS_BATCH_INVALID", "批量数据格式无效", status_code=422)
        if len(records) > MAX_IMPORT_BATCH_SIZE:
            raise AppError(
                "WORKSHOP_PROCESS_BATCH_TOO_LARGE",
                f"单批最多导入 {MAX_IMPORT_BATCH_SIZE} 条车间工序数据",
                status_code=413,
            )

        inserted = versioned = unchanged = skipped = 0
        try:
            for record in records:
                if not isinstance(record, WorkshopProcessRecord):
                    if skip_invalid:
                        skipped += 1
                        continue
                    raise AppError("WORKSHOP_PROCESS_RECORD_INVALID", "车间工序数据格式无效", status_code=422)
                if not record.source_record_id.strip() or not record.process_department.strip():
                    if skip_invalid:
                        skipped += 1
                        continue
                    raise AppError("WORKSHOP_PROCESS_RECORD_INVALID", "车间工序数据缺少关键字段", status_code=422)

                values = record.model_dump()
                canonical = json.dumps(
                    record.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                content_hash = hashlib.sha256(
                    f"{record.source_type}|{record.source_record_id}|{canonical}".encode("utf-8")
                ).hexdigest()
                row = self.session.scalar(
                    select(WorkshopProcessRecordRow).where(
                        WorkshopProcessRecordRow.source_type == record.source_type,
                        WorkshopProcessRecordRow.source_record_id == record.source_record_id,
                        WorkshopProcessRecordRow.is_current.is_(True),
                    )
                )
                if row is None:
                    self.session.add(
                        WorkshopProcessRecordRow(
                            **values,
                            version=1,
                            content_hash=content_hash,
                            is_current=True,
                        )
                    )
                    inserted += 1
                elif row.content_hash == content_hash:
                    unchanged += 1
                else:
                    self.session.execute(
                        update(WorkshopProcessRecordRow)
                        .where(
                            WorkshopProcessRecordRow.source_type == record.source_type,
                            WorkshopProcessRecordRow.source_record_id == record.source_record_id,
                            WorkshopProcessRecordRow.is_current.is_(True),
                        )
                        .values(is_current=False)
                    )
                    self.session.add(
                        WorkshopProcessRecordRow(
                            **values,
                            version=row.version + 1,
                            content_hash=content_hash,
                            is_current=True,
                        )
                    )
                    versioned += 1
            self.session.commit()
            result = {
                "inserted": inserted,
                "versioned": versioned,
                "unchanged": unchanged,
                "total": len(records),
            }
            if skipped:
                result["skipped"] = skipped
            return result
        except AppError:
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError(
                "WORKSHOP_PROCESS_CONFLICT",
                "车间工序数据发生并发冲突，整批数据未保存",
                status_code=409,
            ) from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise AppError(
                "WORKSHOP_PROCESS_DATABASE_ERROR",
                "车间工序数据保存失败，整批数据未保存",
                status_code=503,
            ) from exc
        except Exception as exc:
            self.session.rollback()
            raise AppError(
                "WORKSHOP_PROCESS_IMPORT_FAILED",
                "车间工序数据导入失败，整批数据未保存",
                status_code=422,
            ) from exc

    def list_current(self, department: str) -> list[WorkshopProcessRecordRow]:
        """Return current rows for an already-authorized, clean department name.

        Authorization belongs to the handler/service layer. This repository only
        performs persistence and filtering and never accepts a DepartmentScope.
        """
        if not isinstance(department, str) or not department.strip():
            raise AppError("WORKSHOP_DEPARTMENT_REQUIRED", "必须指定业务部门", status_code=400)
        try:
            return list(
                self.session.scalars(
                    select(WorkshopProcessRecordRow)
                    .where(
                        WorkshopProcessRecordRow.is_current.is_(True),
                        WorkshopProcessRecordRow.process_department == department,
                    )
                    .order_by(WorkshopProcessRecordRow.id)
                ).all()
            )
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise AppError(
                "WORKSHOP_PROCESS_DATABASE_ERROR",
                "车间工序数据读取失败",
                status_code=503,
            ) from exc
        except Exception as exc:
            self.session.rollback()
            raise AppError(
                "WORKSHOP_PROCESS_READ_FAILED",
                "车间工序数据读取失败",
                status_code=503,
            ) from exc
