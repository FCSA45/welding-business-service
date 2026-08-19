from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.dependencies import get_report_service, verify_business_api_key
from app.reports.models import ReportRequest, ReportResult
from app.reports.service import ReportService
from app.config import Settings, get_settings


router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(verify_business_api_key)])


@router.post("/generate", response_model=ReportResult)
def generate_report(
    request: ReportRequest,
    service: ReportService = Depends(get_report_service),
) -> ReportResult:
    return service.generate(request)


@router.get("/files/{filename}", include_in_schema=True)
def download_report_file(
    filename: str,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    base = Path(settings.report_files_dir).resolve()
    path = (base / filename).resolve()
    if path.parent != base or path.suffix.lower() != ".svg" or not path.is_file():
        from app.errors import AppError

        raise AppError("REPORT_FILE_NOT_FOUND", "报表图表文件不存在", status_code=404)
    return FileResponse(path, media_type="image/svg+xml", filename=path.name)
