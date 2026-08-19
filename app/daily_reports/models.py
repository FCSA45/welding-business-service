from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DailyReportStatus(str, Enum):
    SUBMITTED = "submitted"
    PENDING_REVIEW = "pending_review"


class DailyReportUpsertRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    report_date: date
    employee_open_id: str = Field(min_length=1, max_length=128)
    employee_name: str = Field(min_length=1, max_length=200)
    completed_work: str = Field(min_length=1, max_length=4000)
    completed_count: int = Field(default=0, ge=0, le=100000)
    next_plan: str = Field(default="", max_length=4000)
    issues: str = Field(default="", max_length=4000)
    submitted_at: datetime | None = None
    status: DailyReportStatus = DailyReportStatus.SUBMITTED
    source: str = Field(default="manual", min_length=1, max_length=50)
    source_message_id: str | None = Field(default=None, max_length=255)

    @field_validator("source_message_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value or None


class DailyReportRecord(BaseModel):
    id: int
    report_date: date
    employee_open_id: str
    employee_name: str
    completed_work: str
    completed_count: int
    next_plan: str
    issues: str
    submitted_at: datetime
    updated_at: datetime
    version: int
    status: DailyReportStatus
    source: str


class DailyReportListResponse(BaseModel):
    reports: list[DailyReportRecord]
    total: int
