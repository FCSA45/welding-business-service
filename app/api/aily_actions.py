from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_report_service, verify_aily_api_key
from app.reports.models import ReportPeriod, ReportRequest, ReportResult
from app.reports.service import ReportService


router = APIRouter(prefix="/aily/actions", tags=["aily"])


class AilyReportRequest(BaseModel):
    period: ReportPeriod
    anchor_date: date
    requester_id: str | None = None
    chat_id: str | None = None


class AilyReportResponse(BaseModel):
    message: str
    report: ReportResult


@router.post(
    "/generate-report",
    response_model=AilyReportResponse,
    dependencies=[Depends(verify_aily_api_key)],
)
def generate_aily_report(
    request: AilyReportRequest,
    service: ReportService = Depends(get_report_service),
) -> AilyReportResponse:
    report = service.generate(
        ReportRequest(period=request.period, anchor_date=request.anchor_date)
    )
    return AilyReportResponse(message=report.summary, report=report)

