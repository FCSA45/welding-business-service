import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from app.workshop.models import WorkshopProcessRecord
from app.workshop.card_content import WorkshopWorkReportRecord
from app.errors import AppError


PROCESS_RECORDS = TypeAdapter(list[WorkshopProcessRecord])
WORK_REPORT_RECORDS = TypeAdapter(list[WorkshopWorkReportRecord])


def load_mock_process_records(path: str | Path) -> list[WorkshopProcessRecord]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return PROCESS_RECORDS.validate_python(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise AppError("INVALID_WORKSHOP_MOCK_DATA", "车间模拟数据格式无效", status_code=422) from exc


def load_mock_work_report_records(path: str | Path) -> list[WorkshopWorkReportRecord]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return WORK_REPORT_RECORDS.validate_python(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise AppError("INVALID_WORKSHOP_WORK_REPORT_MOCK_DATA", "车间报工模拟数据格式无效", status_code=422) from exc
