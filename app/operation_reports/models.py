from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class OperationDailyReportUpsertRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    report_date: date
    platform: str = Field(default="未指定平台", min_length=1, max_length=100)
    account_name: str = Field(default="未指定账号", min_length=1, max_length=200)
    operator_name: str = Field(min_length=1, max_length=200)
    project_name: str = Field(default="", max_length=300)
    published_count: int = Field(default=0, ge=0, le=100000)
    submitted_script_count: int = Field(default=0, ge=0, le=100000)
    script_data_filled_count: int = Field(default=0, ge=0, le=100000)
    completed_work: str = Field(default="", max_length=4000)
    next_plan: str = Field(default="", max_length=4000)
    issues: str = Field(default="", max_length=4000)
    source: str = Field(default="manual", min_length=1, max_length=50)
    source_row_id: str | None = Field(default=None, max_length=255)


class OperationDailyReportRecord(BaseModel):
    id: int
    report_date: date
    platform: str
    account_name: str
    operator_name: str
    project_name: str
    published_count: int
    submitted_script_count: int
    script_data_filled_count: int
    completed_work: str
    next_plan: str
    issues: str
    source: str
    source_row_id: str | None
    created_at: datetime
    updated_at: datetime


class OperationDailyReportListResponse(BaseModel):
    reports: list[OperationDailyReportRecord]
    total: int


class OperationPublicationCountRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    report_date: date
    platform: str = Field(default="未指定平台", min_length=1, max_length=100)
    account_name: str = Field(default="未指定账号", min_length=1, max_length=200)
    operator_name: str = Field(min_length=1, max_length=200)
    published_count: int = Field(ge=0, le=100000)
    script_count: int = Field(default=0, ge=0, le=100000)
    filled_script_data_count: int = Field(default=0, ge=0, le=100000)
    note: str = Field(default="", max_length=500)
    source_row_id: str | None = Field(default=None, max_length=255)


class OperationPublicationCountResponse(BaseModel):
    id: int
    report_date: date
    platform: str
    account_name: str
    operator_name: str
    published_count: int
    script_count: int
    filled_script_data_count: int
    note: str
    source: str
    duplicate: bool
