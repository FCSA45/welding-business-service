import hashlib
import json
from typing import Protocol

from pydantic import BaseModel

from app.reports.models import SourceRecord


class InvalidRow(BaseModel):
    row_number: int
    errors: list[str]


class SourceBatch(BaseModel):
    source: str
    read_count: int
    records: list[SourceRecord]
    invalid_rows: list[InvalidRow]


class DataSource(Protocol):
    def fetch_records(self) -> SourceBatch: ...


def hash_record(record: SourceRecord) -> str:
    payload = json.dumps(
        [
            record.report_date.isoformat(),
            record.platform,
            record.account_name,
            record.operator_name,
            record.published_count,
            record.script_count,
            record.filled_script_data_count,
            record.note,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
