import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from app.api.aily_actions import router as aily_actions_router
from app.api.daily_reports import router as daily_reports_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.operation_reports import router as operation_reports_router
from app.api.performance_checks import router as performance_checks_router
from app.api.platform import router as platform_router
from app.api.reports import router as reports_router
from app.api.rag_demo import router as rag_demo_router
from app.api.rag_documents import router as rag_documents_router
from app.api.sources import router as sources_router
from app.api.wecom import router as wecom_router
from app.errors import AppError
from app.config import get_settings
from app.sources.periodic_sync import PeriodicSyncRunner, create_periodic_sync_runner
from app.agent_platform.scheduler import PlatformSchedulerRunner
from app.wecom.long_connection import WeComAIBotRunner
from app.wecom.bot_bindings import build_wecom_bot_bindings


def create_app(
    frontend_dist: Path | None = None,
    *,
    enable_periodic_sync: bool = False,
    periodic_sync_runner: PeriodicSyncRunner | None = None,
    enable_platform_scheduler: bool = True,
    platform_scheduler_runner: PlatformSchedulerRunner | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        periodic_sync_task: asyncio.Task[None] | None = None
        platform_scheduler_task: asyncio.Task[None] | None = None
        wecom_aibot_tasks: list[asyncio.Task[None]] = []
        workshop_data_warm_tasks: list[asyncio.Task[None]] = []
        runner = periodic_sync_runner
        scheduler_runner = platform_scheduler_runner
        settings = get_settings()
        if enable_periodic_sync and runner is None:
            if settings.data_source == "tencent_doc":
                runner = create_periodic_sync_runner(settings)
        if enable_periodic_sync and runner is not None:
            periodic_sync_task = asyncio.create_task(runner.run_forever())
            application.state.periodic_sync_task = periodic_sync_task
        if enable_platform_scheduler and scheduler_runner is None:
            scheduler_runner = PlatformSchedulerRunner(settings)
        if enable_platform_scheduler and scheduler_runner is not None and scheduler_runner.is_enabled:
            platform_scheduler_task = asyncio.create_task(scheduler_runner.run_forever())
            application.state.platform_scheduler_task = platform_scheduler_task
        bot_bindings = build_wecom_bot_bindings(settings)
        wecom_runners = {
            binding.key: WeComAIBotRunner(
                settings,
                binding=binding,
            )
            for binding in bot_bindings
        }
        wecom_runner = wecom_runners["packaging"]
        application.state.wecom_aibot_runner = wecom_runner
        application.state.wecom_aibot_runners = wecom_runners
        if scheduler_runner is not None:
            event_loop = asyncio.get_running_loop()

            def send_scheduled_wecom_message(chat_id: str, content: str) -> str:
                future = asyncio.run_coroutine_threadsafe(
                    wecom_runner.send_text(chat_id, content), event_loop
                )
                return future.result(timeout=settings.wecom_timeout_seconds)

            scheduler_runner.delivery_sender = send_scheduled_wecom_message
        for bot_key, department_runner in wecom_runners.items():
            if not department_runner.is_enabled:
                continue
            task = asyncio.create_task(department_runner.run_forever())
            warm_task = asyncio.create_task(department_runner.warm_workshop_data())
            wecom_aibot_tasks.append(task)
            workshop_data_warm_tasks.append(warm_task)
            application.state.__setattr__(f"wecom_aibot_task_{bot_key}", task)
        if periodic_sync_task is not None or platform_scheduler_task is not None:
            await asyncio.sleep(0)
        try:
            yield
        finally:
            tasks = [
                periodic_sync_task, platform_scheduler_task,
                *wecom_aibot_tasks, *workshop_data_warm_tasks,
            ]
            for task in tasks:
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

    application = FastAPI(
        title="绩效核查督导后台",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(knowledge_router, prefix="/api/v1")
    application.include_router(reports_router, prefix="/api/v1")
    application.include_router(rag_demo_router, prefix="/api/v1")
    application.include_router(rag_documents_router, prefix="/api/v1")
    application.include_router(sources_router, prefix="/api/v1")
    application.include_router(aily_actions_router, prefix="/api/v1")
    application.include_router(daily_reports_router, prefix="/api/v1")
    application.include_router(operation_reports_router, prefix="/api/v1")
    application.include_router(performance_checks_router, prefix="/api/v1")
    application.include_router(platform_router, prefix="/api/v1")
    application.include_router(wecom_router, prefix="/api/v1")

    @application.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @application.exception_handler(OperationalError)
    async def database_unavailable_handler(
        request: Request,
        exc: OperationalError,
    ) -> JSONResponse:
        del request, exc
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "SOURCE_UNAVAILABLE",
                    "message": "PostgreSQL 暂时不可用，请稍后重试",
                    "details": None,
                }
            },
        )

    dist = frontend_dist or Path(__file__).resolve().parents[1] / "frontend" / "dist"
    index_file = dist / "index.html"
    if index_file.is_file():
        assets_dir = dist / "assets"
        if assets_dir.is_dir():
            application.mount(
                "/assets",
                StaticFiles(directory=assets_dir),
                name="frontend-assets",
            )

        @application.get("/", include_in_schema=False)
        async def frontend_root() -> FileResponse:
            return FileResponse(index_file)

        @application.get("/{full_path:path}", include_in_schema=False)
        async def frontend_fallback(full_path: str) -> FileResponse:
            protected_roots = {"api", "docs", "redoc", "openapi.json"}
            root_segment = full_path.split("/", maxsplit=1)[0]
            if root_segment in protected_roots:
                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(index_file)

    return application


def create_aily_gateway_app() -> FastAPI:
    application = FastAPI(
        title="Aily Action Gateway",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(aily_actions_router, prefix="/api/v1")

    @application.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @application.exception_handler(OperationalError)
    async def database_unavailable_handler(
        request: Request,
        exc: OperationalError,
    ) -> JSONResponse:
        del request, exc
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "SOURCE_UNAVAILABLE",
                    "message": "PostgreSQL is temporarily unavailable.",
                    "details": None,
                }
            },
        )

    return application


app = create_app(enable_periodic_sync=False)
