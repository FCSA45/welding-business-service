"""Canonical business intent names used by parsers and handlers."""

from __future__ import annotations


class BusinessIntent:
    """String constants for every built-in business route."""

    GENERAL_CHAT = "general_chat"
    WORKSHOP_DEPARTMENT_DAILY_REPORT = "workshop_department_daily_report"
    WORKSHOP_DEPARTMENT_WORK_REPORT = "workshop_department_work_report"

    ALL = frozenset(
        {
            GENERAL_CHAT,
            WORKSHOP_DEPARTMENT_DAILY_REPORT,
            WORKSHOP_DEPARTMENT_WORK_REPORT,
        }
    )
