"""Business-neutral JianDaoYun form-data query interface."""

from __future__ import annotations

from typing import Any

from app.errors import AppError
from app.integrations.jiandaoyun.client import JianDaoYunMCPClient


class JianDaoYunDataAPI:
    def __init__(self, client: JianDaoYunMCPClient, *, page_size: int = 100, max_pages: int = 100) -> None:
        self.client = client
        self.page_size = page_size
        self.max_pages = max_pages

    async def list_records(
        self, *, app_id: str, entry_id: str, fields: list[str],
        conditions: list[dict[str, Any]], relation: str = "and",
    ) -> list[dict[str, Any]]:
        if not app_id or not entry_id:
            raise AppError("JIANDAOYUN_FORM_CONFIG_MISSING", "简道云应用或表单配置缺失", status_code=503)
        await self.client.call_tool("get_tool_help", {"tool_name": "member_data_list"})
        rows: list[dict[str, Any]] = []
        cursor = ""
        seen: set[str] = set()
        for _ in range(self.max_pages):
            arguments: dict[str, Any] = {
                "app_id": app_id, "entry_id": entry_id, "limit": self.page_size,
                "fields": fields, "filter": {"rel": relation, "cond": conditions},
            }
            if cursor:
                arguments["cursor_data_id"] = cursor
            page = _extract_rows(await self.client.call_tool("member_data_list", arguments))
            rows.extend(page)
            if len(page) < self.page_size:
                return rows
            cursor = str(page[-1].get("_id", ""))
            if not cursor:
                raise AppError("JIANDAOYUN_MCP_BAD_PAGE", "简道云分页结果缺少数据编号", status_code=502)
            if cursor in seen:
                raise AppError("JIANDAOYUN_MCP_PAGE_LOOP", "简道云分页游标未向前推进", status_code=502)
            seen.add(cursor)
        raise AppError("JIANDAOYUN_MCP_PAGE_LIMIT", "简道云单次查询页数超过安全上限", status_code=502)


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    value = payload
    for key in ("data", "records", "items", "list"):
        if isinstance(value, dict) and key in value:
            value = value[key]
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise AppError("JIANDAOYUN_MCP_BAD_RESPONSE", "简道云返回了无法识别的数据格式", status_code=502)
    return value
