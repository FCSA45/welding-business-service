from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_operation_daily_report_service,
    get_operation_publication_count_service,
    get_performance_reporting_service,
    verify_business_api_key,
)
from app.operation_reports.models import (
    OperationDailyReportListResponse,
    OperationDailyReportRecord,
    OperationDailyReportUpsertRequest,
    OperationPublicationCountRequest,
    OperationPublicationCountResponse,
)
from app.operation_reports.service import OperationDailyReportService, OperationPublicationCountService
from app.performance_checks.reporting import PerformanceReportingService


router = APIRouter(prefix="/operation-reports", tags=["operation-reports"], dependencies=[Depends(verify_business_api_key)])


@router.get("", response_model=OperationDailyReportListResponse)
def list_operation_reports(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    service: OperationDailyReportService = Depends(get_operation_daily_report_service),
) -> OperationDailyReportListResponse:
    reports = service.list_reports(start_date, end_date)
    return OperationDailyReportListResponse(reports=reports, total=len(reports))


@router.post("", response_model=OperationDailyReportRecord)
@router.post("/official-summaries", response_model=OperationDailyReportRecord)
def submit_operation_report(
    request: OperationDailyReportUpsertRequest,
    service: OperationDailyReportService = Depends(get_operation_daily_report_service),
    reporting: PerformanceReportingService = Depends(get_performance_reporting_service),
) -> OperationDailyReportRecord:
    result = service.upsert(request)
    reporting.rebuild_daily(request.report_date)
    return result


@router.post("/publication-counts", response_model=OperationPublicationCountResponse)
@router.post("/publication-details", response_model=OperationPublicationCountResponse)
def submit_publication_count(
    request: OperationPublicationCountRequest,
    service: OperationPublicationCountService = Depends(get_operation_publication_count_service),
    reporting: PerformanceReportingService = Depends(get_performance_reporting_service),
) -> OperationPublicationCountResponse:
    result = service.submit(request)
    reporting.rebuild_daily(request.report_date)
    return result
