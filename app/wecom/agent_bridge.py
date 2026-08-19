"""Bridge WeCom messages to Cherry locally or Hermes in the cloud.

This service is not a model host. Cherry/Hermes owns intent recognition,
conversation memory, tool selection, and final response generation. The
business service remains the authenticated MCP/business runtime.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from app.config import Settings
from app.errors import AppError
from app.wecom.bot_bindings import WeComBotBinding


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeComAgentResponse:
    request_id: str
    status: str
    message: str


class WeComAgentBridge:
    """Call the configured Cherry or Hermes agent through one boundary."""

    _cherry_toolset_version = "v7"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cherry_sessions: dict[str, str] = {}
        self._cherry_sessions_lock = threading.Lock()

    @property
    def mode(self) -> str:
        return str(getattr(self.settings, "wecom_agent_mode", "cherry_local")).strip().lower()

    @property
    def is_configured(self) -> bool:
        if self.mode == "cherry_local":
            return bool(
                str(getattr(self.settings, "cherry_agent_api_url", "")).strip()
                and str(getattr(self.settings, "cherry_agent_api_key", "")).strip()
            )
        return self.mode == "hermes" and bool(
            str(getattr(self.settings, "hermes_agent_url", "")).strip()
            and str(getattr(self.settings, "hermes_agent_api_key", "")).strip()
        )

    def invoke(
        self,
        *,
        binding: WeComBotBinding,
        requester_id: str,
        chat_id: str,
        message_id: str,
        text: str,
    ) -> WeComAgentResponse:
        if self.mode == "cherry_local":
            return self._invoke_cherry(
                binding=binding,
                requester_id=requester_id,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
            )
        if self.mode != "hermes":
            raise AppError(
                "WECOM_AGENT_BRIDGE_DISABLED",
                "企业微信智能体桥接模式未启用。",
                status_code=503,
            )
        if not self.is_configured:
            raise AppError(
                "HERMES_AGENT_NOT_CONFIGURED",
                "企业微信 Hermes 智能体地址或鉴权密钥尚未配置。",
                status_code=503,
            )

        request_id = message_id or uuid4().hex
        payload = {
            "request_id": request_id,
            "agent_id": binding.agent_id,
            "message": text,
            "channel": "wecom",
            "requester_id": requester_id,
            "chat_id": chat_id,
            "bot_key": binding.key,
            "department": binding.department,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.hermes_agent_api_key}",
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
            "X-WeCom-Bot-Key": binding.key,
        }
        timeout = float(getattr(self.settings, "hermes_agent_timeout_seconds", 60))
        try:
            response = httpx.post(
                self.settings.hermes_agent_url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as exc:
            raise AppError("HERMES_AGENT_TIMEOUT", "Hermes 智能体响应超时，请稍后重试。", status_code=504) from exc
        except httpx.HTTPStatusError as exc:
            raise AppError(
                "HERMES_AGENT_HTTP_ERROR",
                "Hermes 智能体暂时不可用，请稍后重试。",
                status_code=502,
                details={"status_code": exc.response.status_code},
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError("HERMES_AGENT_UNAVAILABLE", "无法连接 Hermes 智能体，请稍后重试。", status_code=502) from exc

        message = self._extract_message(body)
        if not message:
            raise AppError("HERMES_AGENT_INVALID_RESPONSE", "Hermes 智能体返回了无法识别的结果。", status_code=502)
        return WeComAgentResponse(
            request_id=str(body.get("request_id") or request_id),
            status=str(body.get("status") or "ok"),
            message=message,
        )

    def _invoke_cherry(
        self,
        *,
        binding: WeComBotBinding,
        requester_id: str,
        chat_id: str,
        message_id: str,
        text: str,
    ) -> WeComAgentResponse:
        agent_id = str(binding.cherry_agent_id or "").strip()
        if not agent_id and binding.key != "painting":
            agent_id = str(getattr(self.settings, "cherry_agent_id", "")).strip()
        if not self.is_configured or not agent_id:
            raise AppError(
                "CHERRY_AGENT_NOT_CONFIGURED",
                f"{binding.display_name}尚未绑定 Cherry Agent。",
                status_code=503,
            )

        request_id = message_id or uuid4().hex
        scope = "|".join((binding.key, requester_id, chat_id))
        session_id = self._get_cherry_session(scope, agent_id, binding)
        try:
            raw_sse = self._post_cherry_message(agent_id, session_id, text)
        except AppError as exc:
            if exc.code != "CHERRY_AGENT_SESSION_NOT_FOUND":
                raise
            self._forget_cherry_session(scope, session_id)
            session_id = self._create_cherry_session(scope, agent_id, binding)
            raw_sse = self._post_cherry_message(agent_id, session_id, text)

        message = self._extract_cherry_message(raw_sse)
        if not message:
            raise AppError(
                "CHERRY_AGENT_INVALID_RESPONSE",
                "Cherry Agent 返回了无法识别的响应。",
                status_code=502,
            )
        return WeComAgentResponse(request_id=request_id, status="ok", message=message)

    def _configured_default_session(self) -> str:
        return str(getattr(self.settings, "cherry_agent_default_session_id", "")).strip()

    def _get_cherry_session(self, scope: str, agent_id: str, binding: WeComBotBinding) -> str:
        configured = self._configured_default_session()
        if configured:
            return configured
        with self._cherry_sessions_lock:
            existing = self._cherry_sessions.get(scope)
        if existing:
            return existing
        restored = self._find_cherry_session(scope, agent_id)
        return restored or self._create_cherry_session(scope, agent_id, binding)

    def _find_cherry_session(self, scope: str, agent_id: str) -> str:
        expected_name = f"企业微信会话 {self._cherry_toolset_version} {scope[-80:]}"
        base_url = str(getattr(self.settings, "cherry_agent_api_url", "")).rstrip("/")
        api_key = str(getattr(self.settings, "cherry_agent_api_key", "")).strip()
        timeout = float(getattr(self.settings, "cherry_agent_timeout_seconds", 120))
        try:
            response = httpx.get(
                f"{base_url}/v1/agents/{agent_id}/sessions",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            return ""
        rows = body.get("data", []) if isinstance(body, dict) else []
        for row in rows:
            if isinstance(row, dict) and row.get("name") == expected_name:
                session_id = str(row.get("id") or "").strip()
                if session_id:
                    with self._cherry_sessions_lock:
                        self._cherry_sessions[scope] = session_id
                    return session_id
        return ""

    def _forget_cherry_session(self, scope: str, session_id: str) -> None:
        with self._cherry_sessions_lock:
            if self._cherry_sessions.get(scope) == session_id:
                self._cherry_sessions.pop(scope, None)

    @staticmethod
    def _allowed_tools(binding: WeComBotBinding) -> list[str]:
        if binding.key == "painting":
            return [
                "mcp__getPaintingOrderDailyReport",
                "mcp__getPaintingWorkReport",
                "mcp__searchPaintingKnowledge",
                "mcp__getPaintingOrderDetail",
                "mcp__getPaintingWorkReportDetail",
            ]
        return [
            "mcp__getWeldingOrderDailyReport",
            "mcp__getWeldingWorkReport",
            "mcp__searchWeldingKnowledge",
            "mcp__getWeldingOrderDetail",
            "mcp__getWeldingWorkReportDetail",
        ]

    def _create_cherry_session(self, scope: str, agent_id: str, binding: WeComBotBinding) -> str:
        body = self._cherry_post(
            f"/v1/agents/{agent_id}/sessions",
            {
                "name": f"企业微信会话 {self._cherry_toolset_version} {scope[-80:]}",
                "description": "由 welding-business-service 自动创建的企业微信 Cherry 会话",
                "allowed_tools": self._allowed_tools(binding),
                "configuration": {
                    "permission_mode": "bypassPermissions",
                    "max_turns": 100,
                },
            },
            allow_sse=False,
        )
        session_id = str(body.get("id") or "").strip()
        if not session_id:
            raise AppError("CHERRY_AGENT_INVALID_RESPONSE", "Cherry Agent 创建会话失败。", status_code=502)
        with self._cherry_sessions_lock:
            self._cherry_sessions[scope] = session_id
        return session_id

    def _post_cherry_message(self, agent_id: str, session_id: str, text: str) -> str:
        try:
            return self._cherry_post(
                f"/v1/agents/{agent_id}/sessions/{session_id}/messages",
                {"content": text},
                allow_sse=True,
            )
        except AppError as exc:
            if exc.details and exc.details.get("status_code") == 404:
                raise AppError(
                    "CHERRY_AGENT_SESSION_NOT_FOUND",
                    "Cherry Agent 会话不存在。",
                    status_code=502,
                    details=exc.details,
                ) from exc
            raise

    def _cherry_post(self, path: str, payload: dict[str, Any], *, allow_sse: bool) -> Any:
        base_url = str(getattr(self.settings, "cherry_agent_api_url", "")).rstrip("/")
        api_key = str(getattr(self.settings, "cherry_agent_api_key", "")).strip()
        timeout = float(getattr(self.settings, "cherry_agent_timeout_seconds", 120))
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json" if allow_sse else "application/json",
        }
        if not allow_sse:
            try:
                response = httpx.post(
                    f"{base_url}{path}",
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                raise AppError("CHERRY_AGENT_TIMEOUT", "Cherry Agent 响应超时，请稍后重试。", status_code=504) from exc
            except httpx.HTTPStatusError as exc:
                raise AppError(
                    "CHERRY_AGENT_HTTP_ERROR",
                    "Cherry Agent 暂时不可用，请稍后重试。",
                    status_code=502,
                    details={"status_code": exc.response.status_code},
                ) from exc
            except httpx.HTTPError as exc:
                raise AppError("CHERRY_AGENT_UNAVAILABLE", "无法连接 Cherry Agent，请确认 Cherry 正在运行。", status_code=502) from exc
            except ValueError as exc:
                raise AppError("CHERRY_AGENT_INVALID_RESPONSE", "Cherry Agent 返回了无效响应。", status_code=502) from exc

        # Cherry returns an SSE stream. Reading it incrementally prevents a
        # completed answer from being held hostage by a connection that stays
        # open after the finish event.
        chunks: list[str] = []
        saw_finish = False
        try:
            stream_timeout = httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=10.0)
            with httpx.stream(
                "POST",
                f"{base_url}{path}",
                json=payload,
                headers=headers,
                timeout=stream_timeout,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not str(line).startswith("data:"):
                        continue
                    raw = str(line)[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    chunks.append(f"data: {raw}")
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "finish":
                        saw_finish = True
                        break
        except httpx.TimeoutException as exc:
            raise AppError("CHERRY_AGENT_TIMEOUT", "Cherry Agent 响应超时，请稍后重试。", status_code=504) from exc
        except httpx.HTTPStatusError as exc:
            raise AppError(
                "CHERRY_AGENT_HTTP_ERROR",
                "Cherry Agent 暂时不可用，请稍后重试。",
                status_code=502,
                details={"status_code": exc.response.status_code},
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError("CHERRY_AGENT_UNAVAILABLE", "无法连接 Cherry Agent，请确认 Cherry 正在运行。", status_code=502) from exc
        logger.info("Cherry SSE completed path=%s events=%s saw_finish=%s", path, len(chunks), saw_finish)
        return "\n".join(chunks)

    @staticmethod
    def _extract_cherry_message(body: str) -> str:
        """Extract Cherry's final result from its AI SDK SSE stream."""
        final_result = ""
        text_parts: list[str] = []
        for line in body.splitlines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "finish":
                result = event.get("raw", {}).get("result")
                if isinstance(result, str) and result.strip():
                    final_result = result.strip()
            elif event.get("type") == "text-delta":
                value = event.get("text")
                if isinstance(value, str):
                    text_parts.append(value)
        if final_result:
            return final_result
        return max(text_parts, key=len, default="").strip()

    @staticmethod
    def _extract_message(body: Any) -> str:
        if not isinstance(body, dict):
            return ""
        candidates = [
            body.get("message"),
            body.get("content"),
            body.get("answer"),
            (body.get("data") or {}).get("message") if isinstance(body.get("data"), dict) else None,
            (body.get("data") or {}).get("content") if isinstance(body.get("data"), dict) else None,
        ]
        return next((str(value).strip() for value in candidates if str(value or "").strip()), "")
