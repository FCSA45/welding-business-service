"""Enterprise WeCom AIBot transport and admission boundary.

This module deliberately does not parse intent, call a model, or dispatch a
business report.  After admission, messages are forwarded to the configured
Hermes agent bridge.  Business execution remains behind MCP.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.errors import AppError
from app.wecom.access_gate import WeComChannelAccessGate
from app.wecom.agent_bridge import WeComAgentBridge, WeComAgentResponse
from app.wecom.bot_bindings import WeComBotBinding
from app.workshop.adapters import build_workshop_adapter

from app.concurrency import KeyedMutex


logger = logging.getLogger(__name__)


class WeComAIBotRunner:
    """Own the single AIBot WebSocket connection used for receive and send."""

    def __init__(
        self,
        settings: Settings,
        *,
        client=None,
        binding: WeComBotBinding | None = None,
        agent_bridge: WeComAgentBridge | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.strict_department_binding = binding is not None
        self.binding = binding or WeComBotBinding(
            key="default",
            agent_id="workshop-agent",
            display_name="车间智能体",
            department=settings.workshop_report_department,
            bot_id=settings.wecom_aibot_bot_id,
            secret=settings.wecom_aibot_secret,
            ws_url=settings.wecom_aibot_ws_url,
            enabled=settings.wecom_aibot_enabled,
        )
        self.agent_bridge = agent_bridge or WeComAgentBridge(settings)
        self.channel_access_gate = WeComChannelAccessGate(settings)
        self.last_error_code: str | None = None
        self.last_chat_id: str | None = None
        self._active_message_ids: set[str] = set()
        self._completed_message_ids: set[str] = set()
        self._completed_message_order: deque[str] = deque(maxlen=1000)
        self._conversation_mutex = KeyedMutex()

    @property
    def is_enabled(self) -> bool:
        return bool(self.binding.enabled and self.binding.configured)

    @property
    def is_connected(self) -> bool:
        return bool(self.client and getattr(self.client, "is_connected", False))

    @property
    def is_authenticated(self) -> bool:
        return bool(self.client and getattr(self.client, "is_authenticated", False))

    async def run_forever(self) -> None:
        if not self.is_enabled:
            return
        injected_client = self.client is not None
        delay = 1
        while True:
            if self.client is None:
                self.client = self._create_client()
            self.client.on("message.text", self._on_text)
            self.client.on("authenticated", self._on_authenticated)
            self.client.on("disconnected", self._on_disconnected)
            self.client.on("error", self._on_error)
            try:
                await self.client.connect_async()
                delay = 1
                while self.client.is_connected:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                await self.client.disconnect()
                raise
            except Exception as exc:
                self.last_error_code = type(exc).__name__[:80]
                logger.warning(
                    "WeCom AIBot connection retry error_type=%s delay_seconds=%s",
                    type(exc).__name__, delay,
                )
                if injected_client:
                    raise
                self.client = None
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    def _create_client(self):
        try:
            from wecom_aibot_sdk import WSClient
        except ImportError as exc:
            self.last_error_code = "WECOM_AIBOT_SDK_MISSING"
            raise RuntimeError("WeCom AIBot SDK is not installed") from exc
        return WSClient({
            "bot_id": self.binding.bot_id,
            "secret": self.binding.secret,
            "ws_url": self.binding.ws_url,
            "max_reconnect_attempts": 0,
        })

    async def _on_text(self, frame: Any) -> None:
        body = getattr(frame, "body", {}) or {}
        message_id = str(body.get("msgid") or "")
        text = str((body.get("text") or {}).get("content") or "").strip()
        if not all((message_id, text)):
            logger.warning("WeCom AIBot ignored incomplete text frame")
            return
        try:
            sender = self.channel_access_gate.authorize(body, binding=self.binding)
        except AppError as exc:
            self.last_error_code = exc.code
            logger.warning(
                "WeCom AIBot admission denied bot_key=%s error_code=%s",
                self.binding.key,
                exc.code,
            )
            await self._reply_admission_denied(frame)
            return

        requester_id = sender.requester_id
        chat_id = sender.chat_id
        namespaced_message_id = (
            f"{self.binding.key}:{message_id}" if self.strict_department_binding else message_id
        )
        if namespaced_message_id in self._active_message_ids or namespaced_message_id in self._completed_message_ids:
            logger.info("WeCom AIBot ignored duplicate message message_id=%s", message_id)
            return
        self._active_message_ids.add(namespaced_message_id)
        self.last_chat_id = chat_id
        try:
            conversation_key = "|".join((self.binding.key, requester_id, chat_id))
            response = await asyncio.to_thread(
                self._process_text_message,
                namespaced_message_id,
                requester_id,
                chat_id,
                text,
                conversation_key,
            )
            from wecom_aibot_sdk import generate_req_id
            await self.client.reply_stream(
                frame,
                generate_req_id(self.settings.wecom_agent_mode),
                response.message,
                finish=True,
            )
            logger.info(
                "WeCom AIBot message completed message_id=%s agent_request_id=%s",
                message_id,
                response.request_id,
            )
        except Exception as exc:
            self.last_error_code = getattr(exc, "code", type(exc).__name__)[:80]
            logger.exception(
                "WeCom AIBot message failed message_id=%s error_type=%s",
                message_id,
                type(exc).__name__,
            )
            try:
                from wecom_aibot_sdk import generate_req_id
                await self.client.reply_stream(
                    frame,
                    generate_req_id(f"{self.settings.wecom_agent_mode}-error"),
                    self._user_safe_failure_message(exc),
                    finish=True,
                )
            except Exception as reply_exc:
                logger.error(
                    "WeCom AIBot fallback reply failed message_id=%s error_type=%s",
                    message_id,
                    type(reply_exc).__name__,
                )
        finally:
            self._active_message_ids.discard(namespaced_message_id)
            if len(self._completed_message_order) == self._completed_message_order.maxlen:
                expired = self._completed_message_order.popleft()
                self._completed_message_ids.discard(expired)
            self._completed_message_order.append(namespaced_message_id)
            self._completed_message_ids.add(namespaced_message_id)

    def _process_text_message(
        self,
        message_id: str,
        requester_id: str,
        chat_id: str,
        text: str,
        conversation_key: str,
    ) -> WeComAgentResponse:
        """Serialize one conversation before handing it to Hermes."""
        return self._conversation_mutex.run(
            conversation_key,
            lambda: self.agent_bridge.invoke(
                binding=self.binding,
                requester_id=requester_id,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
            ),
        )

    async def _reply_admission_denied(self, frame: Any) -> None:
        """Reply without invoking Hermes, memory, or business services."""
        try:
            from wecom_aibot_sdk import generate_req_id

            await self.client.reply_stream(
                frame,
                generate_req_id("wecom-access-denied"),
                "当前账号无权使用该内部业务机器人。",
                finish=True,
            )
        except Exception as exc:
            logger.warning(
                "WeCom AIBot admission denial reply failed bot_key=%s error_type=%s",
                self.binding.key,
                type(exc).__name__,
            )

    async def warm_workshop_data(self) -> None:
        """Warm only the read-only data adapter; this is not chat handling."""
        if self.settings.workshop_data_adapter != "jiandaoyun_mcp":
            return
        try:
            adapter = build_workshop_adapter(self.settings)
            current_date = datetime.now(ZoneInfo(self.settings.app_timezone)).date()
            await asyncio.to_thread(
                adapter.fetch_plan_records,
                department=self.binding.department,
                start_date=current_date - timedelta(days=1),
                end_date=current_date,
            )
            logger.info("JianDaoYun workshop cache warmed bot_key=%s", self.binding.key)
        except Exception as exc:
            logger.warning("JianDaoYun workshop cache warm failed error_type=%s", type(exc).__name__)

    async def send_text(self, chat_id: str, text: str) -> str:
        if not self.is_authenticated:
            raise AppError(
                "WECOM_AIBOT_NOT_CONNECTED",
                "企业微信 AIBot 长连接尚未认证。",
                status_code=503,
            )
        frame = await self.client.send_message(
            chat_id,
            {"msgtype": "markdown", "markdown": {"content": text}},
        )
        headers = getattr(frame, "headers", {}) or {}
        return str(headers.get("req_id") or "")

    async def connect_for_delivery(self) -> None:
        """Open a short-lived authenticated connection for scheduled delivery."""
        if not self.is_enabled:
            raise AppError(
                "WECOM_AIBOT_DISABLED",
                "企业微信机器人未启用或未配置。",
                status_code=503,
            )
        if self.client is None:
            self.client = self._create_client()
        await self.client.connect_async()
        deadline = asyncio.get_running_loop().time() + self.settings.wecom_timeout_seconds
        while not self.is_authenticated:
            if not self.is_connected or asyncio.get_running_loop().time() >= deadline:
                raise AppError(
                    "WECOM_AIBOT_AUTH_TIMEOUT",
                    "企业微信机器人连接认证超时。",
                    status_code=503,
                )
            await asyncio.sleep(0.1)

    async def send_media(self, chat_id: str, file_path: str) -> str:
        """Upload and proactively send a local image/file to a WeCom chat."""
        if not self.is_authenticated:
            raise AppError(
                "WECOM_AIBOT_NOT_CONNECTED",
                "企业微信 AIBot 长连接尚未认证。",
                status_code=503,
            )
        frame = await self.client.send_media_message(chat_id, file_path)
        headers = getattr(frame, "headers", {}) or {}
        return str(headers.get("req_id") or "")

    async def close_after_delivery(self) -> None:
        if self.client is not None:
            await self.client.disconnect()
            self.client = None

    def _user_safe_failure_message(self, exc: Exception) -> str:
        if isinstance(exc, AppError):
            if exc.code == "CHERRY_AGENT_NOT_CONFIGURED":
                return exc.message
            if exc.code == "WECOM_AGENT_BRIDGE_DISABLED":
                return "当前企业微信通道尚未接入 Hermes 智能体，请先在 Cherry 中测试 MCP，或配置 Hermes 企业微信桥接。"
            if exc.code == "HERMES_AGENT_NOT_CONFIGURED":
                return "企业微信智能体服务尚未配置完成，请联系管理员。"
            if exc.code == "HERMES_AGENT_TIMEOUT":
                return "Hermes 智能体响应超时，请稍后重试。"
            if exc.code in {"HERMES_AGENT_UNAVAILABLE", "HERMES_AGENT_HTTP_ERROR"}:
                return "Hermes 智能体暂时不可用，请稍后重试。"
        return "本次消息暂时未能处理，请稍后重试。"

    async def _on_authenticated(self, *args) -> None:
        del args
        self.last_error_code = None
        logger.info(
            "WeCom AIBot authenticated bot_key=%s department=%s",
            self.binding.key,
            self.binding.department,
        )

    async def _on_disconnected(self, reason=None) -> None:
        logger.warning("WeCom AIBot disconnected reason_type=%s", type(reason).__name__)

    async def _on_error(self, frame=None) -> None:
        del frame
        self.last_error_code = "WECOM_AIBOT_PROTOCOL_ERROR"
        logger.error("WeCom AIBot protocol error")
