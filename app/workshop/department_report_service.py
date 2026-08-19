"""Reusable department order-report use case, independent of any robot channel."""

from __future__ import annotations

from datetime import date, timedelta

from app.workshop.access import DepartmentScope
from app.workshop.adapters import WorkshopProcessAdapter
from app.workshop.department_plan_report import build_department_plan_payload
from app.workshop.department_profiles import DepartmentProfileRegistry


class DepartmentOrderReportService:
    def __init__(
        self,
        adapter: WorkshopProcessAdapter,
        profiles: DepartmentProfileRegistry | None = None,
    ) -> None:
        self.adapter = adapter
        self.profiles = profiles or DepartmentProfileRegistry()

    def generate(
        self, *, department: str, statistics_date: date, timezone: str,
        scope: DepartmentScope | None = None,
    ) -> dict:
        profile = self.profiles.resolve(department)
        records = self.adapter.fetch_plan_records(
            department=profile.name,
            start_date=statistics_date,
            end_date=statistics_date,
            scope=scope,
        )
        payload = build_department_plan_payload(
            records,
            report_date=statistics_date + timedelta(days=1),
            timezone=timezone,
            department=profile.name,
            important_large_centimeters=profile.important_large_centimeters,
            example_limit=profile.example_limit,
        )
        payload["department_code"] = profile.code
        payload["knowledge_files"] = [
            str(path) for path in self.profiles.knowledge_files(profile.name)
        ]
        return payload
