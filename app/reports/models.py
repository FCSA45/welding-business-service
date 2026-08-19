from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SyncRecord(BaseModel):
    """同步明细模型，表示单条运营记录。"""
    report_date: date
    platform: str = "未指定平台"
    account_name: str = "未指定账号"
    operator_name: str
    published_count: int
    script_count: int
    filled_script_data_count: int = 0
    note: str


class ReportPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class SourceRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    report_date: date
    platform: str = Field(default="未指定平台", min_length=1, max_length=100)
    account_name: str = Field(default="未指定账号", min_length=1, max_length=200)
    operator_name: str = Field(min_length=1)
    published_count: int = Field(ge=0)
    script_count: int = Field(ge=0)
    filled_script_data_count: int = Field(default=0, ge=0)
    note: str = Field(default="", max_length=500)
    source: str = "local_csv"
    source_row_id: str | None = None
    source_hash: str | None = None

    @field_validator("operator_name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("operator_name must not be blank")
        return value


class ReportRequest(BaseModel):
    period: ReportPeriod
    anchor_date: date
    operator_name: str | None = None

    @field_validator("operator_name")
    @classmethod
    def normalize_operator_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class OperatorSummary(BaseModel):
    name: str
    published_count: int
    script_count: int


class ReportResult(BaseModel):
    request_id: str
    status: str
    error_code: str | None = None
    period: ReportPeriod
    period_start: date
    period_end: date
    record_count: int
    operator_count: int
    published_total: int
    script_total: int
    operators: list[OperatorSummary]
    invalid_row_count: int = 0
    summary: str
