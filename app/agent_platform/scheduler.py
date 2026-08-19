"""Scheduled delivery through the external Hermes agent runtime."""

import asyncio
import logging
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.agent_platform.repository import ScheduleRepository
from app.config import Settings
from app.db.session import get_session_factory
from app.errors import AppError
from app.wecom.agent_bridge import WeComAgentBridge
from app.wecom.bot_bindings import build_wecom_bot_bindings


logger = logging.getLogger(__name__)


class PlatformScheduleExecutor:
    def __init__(
        self,
        settings: Settings,
        session: Session,
        *,
        delivery_sender: Callable[[str, str], str] | None = None,
    ) -> None:
        self.settings = settings
        self.session = session
        self.schedules = ScheduleRepository(session)
        self.delivery_sender = delivery_sender

    def _deliver(self, schedule, message: str) -> str:
        if schedule.target_type != "wecom_chat":
            return message
        if not schedule.target_id.strip():
            raise AppError(
                "SCHEDULE_TARGET_REQUIRED",
                "WeCom scheduled delivery requires a target chat ID.",
                status_code=422,
            )
        if self.delivery_sender is None:
            raise AppError(
                "SCHEDULE_DELIVERY_UNAVAILABLE",
                "The WeCom delivery channel is not ready.",
                status_code=503,
            )
        message_id = self.delivery_sender(schedule.target_id.strip(), message)
        return f"Delivered to WeCom chat {schedule.target_id} (message_id={message_id or 'unknown'})."

    def run(self, schedule_id: int, scheduled_for: datetime) -> object:
        schedule = self.schedules.require(schedule_id)
        normalized_time = scheduled_for.replace(second=0, microsecond=0)
        if schedule.agent_id == "workshop-agent" and not getattr(
            self.settings, "workshop_report_schedule_enabled", False
        ):
            raise AppError(
                "WORKSHOP_REPORT_SCHEDULE_DISABLED",
                "Workshop report scheduling is disabled.",
                status_code=409,
            )
        if self.schedules.already_ran(schedule.id, normalized_time):
            raise AppError("SCHEDULE_ALREADY_RAN", "This schedule has already run.", status_code=409)
        if schedule.action != "generate_summary":
            return self.schedules.create_run(
                {
                    "schedule_id": schedule.id,
                    "scheduled_for": normalized_time,
                    "status": "failed",
                    "output": "",
                    "error_code": "UNSUPPORTED_SCHEDULE_ACTION",
                }
            )

        period_label = {
            "daily": "daily report",
            "weekly": "weekly report",
            "monthly": "monthly report",
        }[schedule.schedule_type]
        binding = next(
            (
                item
                for item in build_wecom_bot_bindings(self.settings)
                if item.agent_id == schedule.agent_id and item.enabled and item.configured
            ),
            None,
        )
        if binding is None:
            raise AppError(
                "SCHEDULE_AGENT_UNAVAILABLE",
                "The scheduled WeCom agent is not configured.",
                status_code=503,
            )
        response = WeComAgentBridge(self.settings).invoke(
            binding=binding,
            requester_id=f"scheduler:{schedule.id}",
            chat_id=schedule.target_id or f"schedule:{schedule.id}",
            message_id=f"schedule:{schedule.id}:{normalized_time.isoformat()}",
            text=f"Generate the {period_label} summary for the scheduled time {normalized_time.isoformat()}.",
        )
        try:
            output = self._deliver(schedule, response.message)
        except AppError as exc:
            return self.schedules.create_run(
                {
                    "schedule_id": schedule.id,
                    "scheduled_for": normalized_time,
                    "status": "failed",
                    "output": "",
                    "error_code": exc.code,
                }
            )
        except Exception as exc:
            logger.exception("Platform schedule delivery failed schedule_id=%s", schedule.id)
            return self.schedules.create_run(
                {
                    "schedule_id": schedule.id,
                    "scheduled_for": normalized_time,
                    "status": "failed",
                    "output": "",
                    "error_code": type(exc).__name__[:80],
                }
            )

        return self.schedules.create_run(
            {
                "schedule_id": schedule.id,
                "scheduled_for": normalized_time,
                "status": response.status,
                "output": output,
                "error_code": None,
            }
        )


class PlatformSchedulerRunner:
    def __init__(
        self,
        settings: Settings,
        *,
        delivery_sender: Callable[[str, str], str] | None = None,
    ) -> None:
        self.settings = settings
        self.timezone = ZoneInfo(settings.app_timezone)
        self.delivery_sender = delivery_sender

    @property
    def is_enabled(self) -> bool:
        return self.settings.platform_scheduler_enabled

    async def run_forever(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.run_due, datetime.now(self.timezone))
            except Exception:
                logger.exception("Platform scheduler task failed")
            await asyncio.sleep(self.settings.platform_scheduler_poll_seconds)

    def run_due(self, now: datetime) -> None:
        with get_session_factory()() as session:
            repository = ScheduleRepository(session)
            executor = PlatformScheduleExecutor(
                self.settings,
                session,
                delivery_sender=self.delivery_sender,
            )
            scheduled_for = now.replace(second=0, microsecond=0)
            for schedule in repository.list_enabled():
                if schedule.agent_id == "workshop-agent" and not getattr(
                    self.settings, "workshop_report_schedule_enabled", False
                ):
                    continue
                if not self._is_due(schedule, now):
                    continue
                if repository.already_ran(schedule.id, scheduled_for):
                    continue
                try:
                    executor.run(schedule.id, scheduled_for)
                except Exception:
                    logger.exception("Platform schedule %s failed", schedule.id)

    @staticmethod
    def _is_due(schedule, now: datetime) -> bool:
        if now.hour != schedule.run_time.hour or now.minute != schedule.run_time.minute:
            return False
        if schedule.schedule_type == "weekly":
            return schedule.day_of_week == now.weekday()
        if schedule.schedule_type == "monthly":
            return schedule.day_of_month == now.day
        return schedule.schedule_type == "daily"
