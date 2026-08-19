from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_performance_check_service, get_performance_reporting_service, verify_business_api_key
from app.errors import AppError
from app.performance_checks.models import (
    DailyAggregateResult,
    PerformanceCheckRequest,
    PerformanceCheckResult,
    WeeklySnapshotListResponse,
    WeeklySnapshotRecord,
)
from app.performance_checks.reporting import PerformanceReportingService
from app.performance_checks.service import PerformanceCheckService


router = APIRouter(prefix="/performance-checks", tags=["performance-checks"], dependencies=[Depends(verify_business_api_key)])


@router.post("/generate", response_model=PerformanceCheckResult)
def generate_performance_check(
    request: PerformanceCheckRequest,
    service: PerformanceCheckService = Depends(get_performance_check_service),
) -> PerformanceCheckResult:
    return service.generate(request)


@router.post("/daily-aggregates/{report_date}", response_model=DailyAggregateResult)
def rebuild_daily_aggregate(
    report_date: date,
    service: PerformanceReportingService = Depends(get_performance_reporting_service),
) -> DailyAggregateResult:
    return service.rebuild_daily(report_date)


@router.post("/weekly-snapshots", response_model=WeeklySnapshotRecord)
def generate_weekly_snapshot(
    anchor_date: date,
    service: PerformanceReportingService = Depends(get_performance_reporting_service),
) -> WeeklySnapshotRecord:
    return service.generate_weekly(anchor_date)


@router.get("/weekly-snapshots", response_model=WeeklySnapshotListResponse)
def list_weekly_snapshots(
    limit: int = Query(default=20, ge=1, le=100),
    service: PerformanceReportingService = Depends(get_performance_reporting_service),
) -> WeeklySnapshotListResponse:
    snapshots = service.list_snapshots(limit)
    return WeeklySnapshotListResponse(snapshots=snapshots, total=len(snapshots))


@router.get("/weekly-snapshots/{snapshot_id}", response_model=WeeklySnapshotRecord)
def get_weekly_snapshot(
    snapshot_id: int,
    service: PerformanceReportingService = Depends(get_performance_reporting_service),
) -> WeeklySnapshotRecord:
    snapshot = service.get_snapshot(snapshot_id)
    if snapshot is None:
        raise AppError("SNAPSHOT_NOT_FOUND", "周报版本不存在", status_code=404)
    return snapshot
