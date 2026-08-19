import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.agent_platform.repository import ConversationRepository
from app.config import Settings
from app.db.session import get_session_factory


logger = logging.getLogger(__name__)


class ConversationLeaseMonitor:
    """Checks durable message leases and writes privacy-safe operational logs."""

    def __init__(self, settings: Settings, *, session_factory=None) -> None:
        self.settings = settings
        self.session_factory = session_factory or get_session_factory()
        self._last_alert_at: datetime | None = None

    @property
    def is_enabled(self) -> bool:
        return self.settings.conversation_lease_monitor_enabled

    async def run_forever(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.check_once)
            except Exception:
                logger.exception("Conversation lease monitor failed")
            await asyncio.sleep(self.settings.conversation_lease_monitor_interval_seconds)

    def check_once(self) -> dict[str, int]:
        with self.session_factory() as session:
            health = ConversationRepository(session).lease_health()
        if not health["expired"] and not health["failed"]:
            return health

        now = datetime.now(timezone.utc)
        cooldown = timedelta(seconds=self.settings.conversation_lease_alert_cooldown_seconds)
        if self._last_alert_at is None or now - self._last_alert_at >= cooldown:
            logger.warning("conversation_lease_unhealthy health=%s", health)
            self._last_alert_at = now
        return health
