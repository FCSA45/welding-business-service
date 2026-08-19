from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_daily_report_service, verify_business_api_key
from app.daily_reports.models import (
    DailyReportListResponse,
    DailyReportRecord,
    DailyReportUpsertRequest,
)
from app.daily_reports.service import DailyReportService


router = APIRouter(prefix="/daily-reports", tags=["daily-reports"], dependencies=[Depends(verify_business_api_key)])


@router.get("", response_model=DailyReportListResponse)
def list_daily_reports(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    service: DailyReportService = Depends(get_daily_report_service),
) -> DailyReportListResponse:
    reports = service.list_reports(start_date, end_date)
    return DailyReportListResponse(reports=reports, total=len(reports))


@router.post("", response_model=DailyReportRecord)
def submit_daily_report(
    request: DailyReportUpsertRequest,
    service: DailyReportService = Depends(get_daily_report_service),
) -> DailyReportRecord:
    return service.submit(request)
