import secrets

from fastapi import Depends
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.agent_platform.repository import KnowledgeRepository
from app.config import Settings, get_settings
from app.db.repositories import (
    SqlAlchemyDailyReportRepository,
    SqlAlchemyOperationDailyReportRepository,
    SqlAlchemyOperationRecordRepository,
    SqlAlchemyPerformanceCheckRepository,
    SqlAlchemyPerformanceReportingRepository,
    SqlAlchemyReportRecordRepository,
    SqlAlchemySyncRunRepository,
)
from app.db.session import get_db_session
from app.daily_reports.service import DailyReportService
from app.operation_reports.service import (
    OperationDailyReportService,
    OperationPublicationCountService,
)
from app.reports.service import ReportService
from app.performance_checks.service import PerformanceCheckService
from app.performance_checks.reporting import PerformanceReportingService
from app.sources.local_csv import LocalCsvSource
from app.sources.service import SyncRecordService, SyncService
from app.sources.tencent_doc import TencentDocSource
from app.agent_platform.search import KnowledgeSearchService
from app.knowledge.service import KnowledgeService


aily_bearer = HTTPBearer(auto_error=False)
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)
business_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_knowledge_service(
    session: Session = Depends(get_db_session),
) -> KnowledgeService:
    return KnowledgeService(KnowledgeSearchService(KnowledgeRepository(session)))


def get_daily_report_service(
    session: Session = Depends(get_db_session),
) -> DailyReportService:
    return DailyReportService(SqlAlchemyDailyReportRepository(session))


def get_report_service(
    session: Session = Depends(get_db_session),
) -> ReportService:
    return ReportService(SqlAlchemyReportRecordRepository(session))


def get_performance_check_service(
    session: Session = Depends(get_db_session),
) -> PerformanceCheckService:
    return PerformanceCheckService(SqlAlchemyPerformanceCheckRepository(session))


def get_performance_reporting_service(
    session: Session = Depends(get_db_session),
) -> PerformanceReportingService:
    return PerformanceReportingService(
        PerformanceCheckService(SqlAlchemyPerformanceCheckRepository(session)),
        SqlAlchemyPerformanceReportingRepository(session),
    )


def get_operation_daily_report_service(
    session: Session = Depends(get_db_session),
) -> OperationDailyReportService:
    return OperationDailyReportService(SqlAlchemyOperationDailyReportRepository(session))


def get_operation_publication_count_service(
    session: Session = Depends(get_db_session),
) -> OperationPublicationCountService:
    return OperationPublicationCountService(SqlAlchemyOperationRecordRepository(session))


def get_sync_record_service(
    session: Session = Depends(get_db_session),
) -> SyncRecordService:
    return SyncRecordService(SqlAlchemyReportRecordRepository(session))


def build_sync_service(settings: Settings, session: Session) -> SyncService:
    if settings.data_source == "local_csv":
        source_factory = lambda: LocalCsvSource(settings.local_csv_path)
    elif settings.data_source == "tencent_doc":
        source_factory = lambda: TencentDocSource(
            settings.tencent_doc_url,
            settings.tencent_doc_sheet_id,
            timeout_seconds=settings.tencent_doc_timeout_seconds,
        )
    else:
        from app.errors import AppError

        raise AppError(
            "SOURCE_NOT_CONFIGURED",
            f"Unsupported data source: {settings.data_source}",
            status_code=503,
        )
    return SyncService(
        source_factory=source_factory,
        record_repository=SqlAlchemyOperationRecordRepository(session),
        run_repository=SqlAlchemySyncRunRepository(session),
    )


def get_sync_service(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
) -> SyncService:
    return build_sync_service(settings, session)


def verify_aily_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(aily_bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    valid = (
        credentials is not None
        and credentials.scheme.lower() == "bearer"
        and bool(settings.aily_action_api_key)
        and secrets.compare_digest(
            credentials.credentials,
            settings.aily_action_api_key,
        )
    )
    if not valid:
        from app.errors import AppError

        raise AppError(
            "UNAUTHORIZED",
            "Aily Action 鉴权失败",
            status_code=401,
        )


def verify_admin_api_key(
    api_key: str | None = Depends(admin_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.platform_admin_api_key:
        from app.errors import AppError

        raise AppError(
            "ADMIN_KEY_NOT_CONFIGURED",
            "后台管理密钥尚未配置",
            status_code=503,
        )
    if api_key is None or not secrets.compare_digest(api_key, settings.platform_admin_api_key):
        from app.errors import AppError

        raise AppError(
            "UNAUTHORIZED",
            "后台管理鉴权失败",
            status_code=401,
        )


def verify_business_api_key(
    api_key: str | None = Depends(business_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """Require a business API key; accept the admin key for recovery access."""
    configured_keys = [
        key for key in (settings.business_api_key, settings.platform_admin_api_key) if key
    ]
    if not configured_keys:
        from app.errors import AppError

        raise AppError(
            "BUSINESS_KEY_NOT_CONFIGURED",
            "业务 API 密钥尚未配置",
            status_code=503,
        )
    if api_key is None or not any(
        secrets.compare_digest(api_key, expected) for expected in configured_keys
    ):
        from app.errors import AppError

        raise AppError("UNAUTHORIZED", "业务 API 鉴权失败", status_code=401)
