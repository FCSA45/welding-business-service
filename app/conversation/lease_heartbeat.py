import logging
import threading

from app.agent_platform.repository import ConversationRepository
from app.db.session import get_session_factory


logger = logging.getLogger(__name__)


class MessageLeaseHeartbeat:
    """Renews a lease using fresh DB sessions; never shares request sessions across threads."""

    def __init__(
        self, *, message_id: int, lease_owner: str, lease_seconds: int,
        session_factory=None, interval_seconds: float | None = None,
        max_error_count: int = 3,
    ) -> None:
        self.message_id = message_id
        self.lease_owner = lease_owner
        self.lease_seconds = lease_seconds
        self.session_factory = session_factory or get_session_factory()
        self.interval_seconds = interval_seconds or max(5.0, lease_seconds / 3)
        if max_error_count < 1:
            raise ValueError("max_error_count must be positive")
        self.max_error_count = max_error_count
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.lease_lost = False
        self.error_count = 0
        self.failure_limit_reached = False

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, name="message-lease-heartbeat", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=min(5.0, self.interval_seconds + 1))
        return False

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                with self.session_factory() as session:
                    renewed = ConversationRepository(session).renew_claim(
                        message_id=self.message_id, lease_owner=self.lease_owner,
                        lease_seconds=self.lease_seconds,
                    )
                if not renewed:
                    self.lease_lost = True
                    logger.error("Message lease heartbeat lost ownership message_id=%s", self.message_id)
                    return
            except Exception:
                self.error_count += 1
                if self.error_count >= self.max_error_count:
                    self.failure_limit_reached = True
                    self._stop.set()
                    logger.exception(
                        "Message lease heartbeat stopped after repeated failures "
                        "message_id=%s error_count=%s",
                        self.message_id,
                        self.error_count,
                    )
                    return
                logger.exception(
                    "Message lease heartbeat failed message_id=%s error_count=%s/%s",
                    self.message_id,
                    self.error_count,
                    self.max_error_count,
                )
