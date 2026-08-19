import re
from collections.abc import Callable
from datetime import date, timedelta
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.errors import AppError
from app.reports.models import SourceRecord
from app.sources.base import InvalidRow, SourceBatch, hash_record
from app.sources.tencent_sheet_codec import decode_tencent_sheet


HEADER_ALIASES = {
    "report_date": ("report_date", "\u65e5\u671f"),
    "operator_name": ("operator_name", "\u59d3\u540d"),
    "published_count": ("published_count", "\u53d1\u5e03\u6570\u91cf"),
    "script_count": ("script_count", "\u811a\u672c\u6570\u91cf"),
    "note": ("note", "\u5907\u6ce8"),
}
SHEET_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class TencentDocSource:
    source_name = "tencent_doc"

    def __init__(
        self,
        doc_url: str,
        sheet_id: str,
        *,
        timeout_seconds: int = 10,
        payload_fetcher: Callable[[], str] | None = None,
    ) -> None:
        self.doc_url = doc_url
        self.sheet_id = sheet_id
        self.timeout_seconds = timeout_seconds
        self.payload_fetcher = payload_fetcher

    def fetch_records(self) -> SourceBatch:
        self._validate_configuration()
        payload = self._fetch_payload()
        try:
            rows = decode_tencent_sheet(payload)
        except (UnicodeDecodeError, ValueError) as exc:
            raise AppError(
                "INVALID_SOURCE_DATA",
                "Tencent sheet data could not be decoded",
                status_code=422,
            ) from exc
        if not rows:
            raise AppError(
                "INVALID_SOURCE_DATA",
                "Tencent sheet is empty",
                status_code=422,
            )

        field_map = self._resolve_headers(rows[0])
        records: list[SourceRecord] = []
        invalid_rows: list[InvalidRow] = []
        read_count = 0
        for row_number, row in enumerate(rows[1:], start=2):
            if not any(str(value).strip() for value in row):
                continue
            read_count += 1
            values = {
                canonical: self._cell(row, column_index)
                for canonical, column_index in field_map.items()
            }
            values["report_date"] = self._normalize_date(values["report_date"])
            try:
                record = SourceRecord(
                    **values,
                    source=self.source_name,
                    source_row_id=f"{self.sheet_id}:{row_number}",
                )
            except ValidationError as exc:
                invalid_rows.append(
                    InvalidRow(
                        row_number=row_number,
                        errors=[self._format_error(item) for item in exc.errors()],
                    )
                )
                continue
            record.source_hash = hash_record(record)
            records.append(record)

        return SourceBatch(
            source=self.source_name,
            read_count=read_count,
            records=records,
            invalid_rows=invalid_rows,
        )

    def _fetch_payload(self) -> str:
        if self.payload_fetcher is not None:
            return self.payload_fetcher()
        from app.sources.tencent_doc_client import TencentDocClient

        return TencentDocClient(
            self.doc_url,
            self.sheet_id,
            timeout_seconds=self.timeout_seconds,
        ).fetch_payload()

    def _validate_configuration(self) -> None:
        parsed = urlsplit(self.doc_url)
        valid_url = (
            parsed.scheme == "https"
            and parsed.hostname == "docs.qq.com"
            and parsed.path.startswith("/sheet/")
        )
        if not valid_url or not SHEET_ID_PATTERN.fullmatch(self.sheet_id):
            raise AppError(
                "SOURCE_NOT_CONFIGURED",
                "Tencent document source is not configured safely",
                status_code=503,
            )

    @staticmethod
    def _resolve_headers(headers: list[str | int | float]) -> dict[str, int]:
        available = {str(name).strip(): index for index, name in enumerate(headers)}
        resolved: dict[str, int] = {}
        missing: list[str] = []
        for canonical, aliases in HEADER_ALIASES.items():
            actual = next((available[name] for name in aliases if name in available), None)
            if actual is None and canonical == "note":
                continue
            if actual is None:
                missing.append(canonical)
            else:
                resolved[canonical] = actual
        if missing:
            raise AppError(
                "INVALID_SOURCE_DATA",
                "Tencent sheet is missing required columns",
                status_code=422,
                details={"missing_columns": missing},
            )
        if "note" not in resolved:
            resolved["note"] = -1
        return resolved

    @staticmethod
    def _cell(row: list[str | int | float], column_index: int) -> str | int | float:
        if column_index < 0 or column_index >= len(row):
            return ""
        value = row[column_index]
        return value.strip() if isinstance(value, str) else value

    @staticmethod
    def _normalize_date(value: str | int | float) -> str | date:
        if isinstance(value, (int, float)):
            if value < 1 or float(value).is_integer() is False:
                return str(value)
            return date(1899, 12, 30) + timedelta(days=int(value))
        return value

    @staticmethod
    def _format_error(error: dict) -> str:
        location = ".".join(str(part) for part in error.get("loc", ()))
        return f"{location}: {error.get('msg', 'invalid value')}"
