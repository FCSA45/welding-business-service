import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.orm import Session

from app.api.dependencies import build_sync_service
from app.config import Settings
from app.db.session import get_session_factory
from app.sources.service import SyncService


logger = logging.getLogger(__name__)

AsyncSleeper = Callable[[float], Awaitable[None]]
BlockingRunner = Callable[[Callable[[], None]], Awaitable[None]]
SessionFactory = Callable[[], Session]
ServiceBuilder = Callable[[Settings, Session], SyncService]


class PeriodicSyncRunner:
    def __init__(
        self,
        sync_once: Callable[[], None],
        interval_seconds: int,
        *,
        sleeper: AsyncSleeper = asyncio.sleep,
        run_blocking: BlockingRunner = asyncio.to_thread,
    ) -> None:
        self.sync_once = sync_once
        self.interval_seconds = interval_seconds
        self.sleeper = sleeper
        self.run_blocking = run_blocking

    async def run_once(self) -> bool:
        try:
            await self.run_blocking(self.sync_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic Tencent synchronization failed")
            return False
        return True

    async def run_forever(self) -> None:
        while True:
            await self.run_once()
            await self.sleeper(self.interval_seconds)


def create_periodic_sync_runner(
    settings: Settings,
    *,
    session_factory: SessionFactory | None = None,
    service_builder: ServiceBuilder = build_sync_service,
    sleeper: AsyncSleeper = asyncio.sleep,
    run_blocking: BlockingRunner = asyncio.to_thread,
) -> PeriodicSyncRunner:
    resolved_session_factory = session_factory or get_session_factory()

    def sync_once() -> None:
        session = resolved_session_factory()
        try:
            service_builder(settings, session).sync()
        finally:
            session.close()

    return PeriodicSyncRunner(
        sync_once,
        settings.tencent_sync_interval_seconds,
        sleeper=sleeper,
        run_blocking=run_blocking,
    )

