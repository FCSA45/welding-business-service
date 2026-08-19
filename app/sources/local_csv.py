import csv
from pathlib import Path

from pydantic import ValidationError

from app.errors import AppError
from app.reports.models import SourceRecord
from app.sources.base import InvalidRow, SourceBatch, hash_record


HEADER_ALIASES = {
    "report_date": ("report_date", "日期"),
    "operator_name": ("operator_name", "姓名"),
    "published_count": ("published_count", "发布数量"),
    "script_count": ("script_count", "脚本数量"),
    "note": ("note", "备注"),
}


class LocalCsvSource:
    source_name = "local_csv"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch_records(self) -> SourceBatch:
        if not self.path.is_file():
            raise AppError(
                "SOURCE_NOT_CONFIGURED",
                f"CSV 数据文件不存在：{self.path}",
                status_code=503,
            )
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            field_map = self._resolve_headers(reader.fieldnames or [])
            records: list[SourceRecord] = []
            invalid_rows: list[InvalidRow] = []
            read_count = 0
            for row_number, raw_row in enumerate(reader, start=2):
                if not any((value or "").strip() for value in raw_row.values()):
                    continue
                read_count += 1
                values = {
                    canonical: (raw_row.get(actual) or "").strip()
                    for canonical, actual in field_map.items()
                }
                try:
                    record = SourceRecord(
                        **values,
                        source=self.source_name,
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

    @staticmethod
    def _resolve_headers(fieldnames: list[str]) -> dict[str, str]:
        available = {name.strip(): name for name in fieldnames if name is not None}
        resolved: dict[str, str] = {}
        missing: list[str] = []
        for canonical, aliases in HEADER_ALIASES.items():
            actual = next((available[alias] for alias in aliases if alias in available), None)
            if actual is None and canonical == "note":
                continue
            if actual is None:
                missing.append(canonical)
            else:
                resolved[canonical] = actual
        if missing:
            raise AppError(
                "INVALID_SOURCE_DATA",
                "CSV 缺少必填列",
                status_code=422,
                details={"missing_columns": missing},
            )
        if "note" not in resolved:
            resolved["note"] = "__missing_note__"
        return resolved

    @staticmethod
    def _format_error(error: dict) -> str:
        location = ".".join(str(part) for part in error.get("loc", ()))
        return f"{location}: {error.get('msg', 'invalid value')}"
