"""Validated parameter contract between the Cherry model and workshop MCP tools."""

from __future__ import annotations

import re
from datetime import date

from app.errors import AppError


def parse_statistics_date(value: str | None) -> date | None:
    """Accept the model's ISO date plus common Chinese/period separators."""
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    normalized = re.sub(r"[年/月.]", "-", cleaned.replace("日", ""))
    parts = normalized.split("-")
    if len(parts) == 3:
        normalized = "-".join((parts[0], parts[1].zfill(2), parts[2].zfill(2)))
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise AppError(
            "WORKSHOP_STATISTICS_DATE_INVALID",
            "统计日期格式无效，请使用 YYYY-MM-DD",
            status_code=400,
        ) from exc
