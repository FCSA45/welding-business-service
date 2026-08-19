from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_sync_record_service, get_sync_service, verify_business_api_key
from app.config import Settings, get_settings
from app.errors import AppError
from app.reports.models import SyncRecord
from app.sources.service import SyncRecordService, SyncResult, SyncService


router = APIRouter(prefix="/sources", tags=["sources"], dependencies=[Depends(verify_business_api_key)])


class SyncRequest(BaseModel):
    source: str = "local_csv"
    force: bool = False


class SyncRecordsResponse(BaseModel):
    records: list[SyncRecord]
    total: int


@router.post("/sync", response_model=SyncResult)
def sync_source(
    request: SyncRequest,
    service: SyncService = Depends(get_sync_service),
    settings: Settings = Depends(get_settings),
) -> SyncResult:
    if request.source != settings.data_source:
        raise AppError(
            "SOURCE_NOT_CONFIGURED",
            f"未配置数据源：{request.source}",
            status_code=503,
        )
    return service.sync()


@router.get("/records", response_model=SyncRecordsResponse)
def get_source_records(
    service: SyncRecordService = Depends(get_sync_record_service),
    settings: Settings = Depends(get_settings),
) -> SyncRecordsResponse:
    records = service.get_all_records(settings.data_source)
    return SyncRecordsResponse(records=records, total=len(records))
