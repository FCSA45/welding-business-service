"""Transport-level JianDaoYun MCP client with a safe, reusable call API."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.errors import AppError


DEFAULT_READ_ONLY_TOOLS = frozenset({
    "get_tool_help", "get_tool_schema", "member_app_list",
    "member_app_entry_list", "member_app_entry_widget_list",
    "member_data_get", "member_data_list",
})


def unwrap_mcp_result(result: Any) -> Any:
    if getattr(result, "isError", False):
        raise AppError("JIANDAOYUN_MCP_QUERY_FAILED", "简道云数据查询失败", status_code=502)
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    texts = [item.text for item in getattr(result, "content", []) if getattr(item, "type", None) == "text"]
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return texts[0]
    return texts


class JianDaoYunMCPClient:
    """Generic allow-listed MCP caller; business code never manages transports."""

    def __init__(
        self, url: str, *, timeout_seconds: int = 30, retry_max_attempts: int = 4,
        allowed_tools=frozenset(DEFAULT_READ_ONLY_TOOLS),
    ) -> None:
        if not url:
            raise AppError("JIANDAOYUN_MCP_URL_MISSING", "未配置简道云 MCP URL", status_code=503)
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._retry_max_attempts = retry_max_attempts
        self._allowed_tools = frozenset(allowed_tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._authorize(name)
        last_error: AppError | None = None
        for attempt in range(self._retry_max_attempts):
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    async with self.connection() as call:
                        return await call(name, arguments)
            except TimeoutError as exc:
                # A hard end-to-end deadline includes connection, MCP
                # initialization and tool execution. Do not multiply it by retries.
                raise AppError(
                    "JIANDAOYUN_MCP_TIMEOUT",
                    "简道云数据源响应超时，请稍后重试",
                    status_code=504,
                ) from exc
            except AppError as exc:
                if exc.code not in {"JIANDAOYUN_MCP_UNAVAILABLE", "JIANDAOYUN_MCP_RATE_LIMITED"}:
                    raise
                last_error = exc
                if attempt < self._retry_max_attempts - 1:
                    retry_after = float((exc.details or {}).get("retry_after", 0))
                    await asyncio.sleep(retry_after or min(8, 2 ** attempt))
        raise last_error or AppError("JIANDAOYUN_MCP_UNAVAILABLE", "简道云数据源暂时不可用", status_code=502)

    @asynccontextmanager
    async def connection(self):
        try:
            timeout = httpx.Timeout(self._timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as http_client:
                async with streamable_http_client(self._url, http_client=http_client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()

                        async def call(name: str, arguments: dict[str, Any]) -> Any:
                            self._authorize(name)
                            return unwrap_mcp_result(await session.call_tool(name, arguments=arguments))

                        yield call
        except AppError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After", "")
                try:
                    delay = max(0.0, float(retry_after))
                except ValueError:
                    delay = 0.0
                raise AppError(
                    "JIANDAOYUN_MCP_RATE_LIMITED", "简道云请求过于频繁", status_code=429,
                    details={"retry_after": delay},
                ) from exc
            raise AppError("JIANDAOYUN_MCP_UNAVAILABLE", "简道云数据源暂时不可用", status_code=502) from exc
        except Exception as exc:
            raise AppError("JIANDAOYUN_MCP_UNAVAILABLE", "简道云数据源暂时不可用", status_code=502) from exc

    def _authorize(self, name: str) -> None:
        if name not in self._allowed_tools:
            raise AppError("JIANDAOYUN_MCP_WRITE_FORBIDDEN", "连接策略禁止调用该简道云工具", status_code=403)


# Backwards-compatible name for callers that explicitly request read-only mode.
ReadOnlyJianDaoYunMCPClient = JianDaoYunMCPClient
