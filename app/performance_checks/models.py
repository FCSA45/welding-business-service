from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.reports.models import ReportPeriod


CheckStatus = Literal["matched", "mismatch", "missing_platform", "missing_report"]


class PerformanceCheckRequest(BaseModel):
    period: ReportPeriod
    anchor_date: date
    operator_name: str | None = None


class PerformanceCheckItem(BaseModel):
    report_date: date
    platform: str
    account_name: str
    operator_name: str
    reported_published_count: int
    actual_published_count: int
    publication_difference: int
    reported_script_count: int
    actual_script_count: int
    filled_script_data_count: int
    script_data_completeness_rate: float
    publication_agreement_rate: float
    status: CheckStatus


class PerformanceCheckResult(BaseModel):
    period: ReportPeriod
    period_start: date
    period_end: date
    row_count: int
    matched_count: int
    review_count: int
    reported_published_total: int
    actual_published_total: int
    items: list[PerformanceCheckItem]
    summary: str


class DailyAggregateResult(BaseModel):
    report_date: date
    row_count: int
    matched_count: int
    review_count: int


class WeeklySnapshotRecord(BaseModel):
    id: int
    period_type: str
    period_start: date
    period_end: date
    version: int
    status: str
    payload: dict
    generated_at: datetime


class WeeklySnapshotListResponse(BaseModel):
    snapshots: list[WeeklySnapshotRecord]
    total: int
