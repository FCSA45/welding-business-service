from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.errors import AppError
from app.workshop.mock_source import load_mock_process_records
from app.workshop.models import WorkshopProcessRecord
from app.workshop.access import DepartmentScope


class WorkshopProcessAdapter(Protocol):
    """All ERP/MES adapters return validated process records."""

    def fetch_records(self, *, department: str, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]: ...
    def fetch_overdue_records(self, *, department: str, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]: ...
    def fetch_plan_records(self, *, department: str, start_date, end_date, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]: ...
    def fetch_order_records(self, *, department: str, product_order_no: str, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]: ...


class MockWorkshopProcessAdapter:
    def __init__(self, path: str | Path, *, allow_unscoped: bool = False) -> None:
        self.path = path
        self.allow_unscoped = allow_unscoped

    def fetch_records(self, *, department: str = "", scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]:
        if not department and self.allow_unscoped:
            return load_mock_process_records(self.path)
        department = scope.require(department) if scope else _require_department(department)
        records = load_mock_process_records(self.path)
        return [record for record in records if record.process_department == department]

    def fetch_overdue_records(self, *, department: str, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        current_date = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        return [
            record for record in self.fetch_records(department=department, scope=scope)
            if record.process_status in {"待生产", "未生产"}
            and (record.planned_completion_at.date() < current_date or record.delivery_date < current_date)
        ]

    def fetch_plan_records(self, *, department: str, start_date, end_date, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]:
        return [
            record for record in self.fetch_records(department=department, scope=scope)
            if start_date <= record.planned_completion_at.date() <= end_date
        ]

    def fetch_order_records(self, *, department: str, product_order_no: str, scope: DepartmentScope | None = None) -> list[WorkshopProcessRecord]:
        department = scope.require(department) if scope else _require_department(department)
        wanted = product_order_no.strip()
        if not wanted:
            raise AppError("WORKSHOP_ORDER_REQUIRED", "必须提供订单号", status_code=400)
        return [
            record for record in self.fetch_records(department=department, scope=scope)
            if record.product_order_no == wanted
        ]

def build_workshop_adapter(settings: Settings) -> WorkshopProcessAdapter:
    """Configuration is the only supported adapter switch point."""
    if settings.workshop_data_adapter == "mock":
        if settings.app_env.lower() in {"production", "prod"} and not settings.workshop_allow_mock_in_production:
            raise AppError("WORKSHOP_MOCK_FORBIDDEN", "生产环境禁止使用车间模拟数据源", status_code=503)
        return MockWorkshopProcessAdapter(
            settings.workshop_mock_data_path,
            allow_unscoped=settings.app_env.lower() not in {"production", "prod"},
        )
    if settings.workshop_data_adapter == "jiandaoyun_mcp":
        from app.workshop.jiandaoyun_mcp import JianDaoYunMCPWorkshopAdapter

        return JianDaoYunMCPWorkshopAdapter(settings)
    if settings.workshop_data_adapter == "jiandaoyun":
        raise AppError("WORKSHOP_ADAPTER_NOT_IMPLEMENTED", "简道云车间数据适配器尚未完成", status_code=503)
    raise AppError("WORKSHOP_ADAPTER_INVALID", "未知的车间数据适配器", status_code=503)


def _require_department(department: str) -> str:
    value = department.strip()
    if not value:
        raise AppError("WORKSHOP_DEPARTMENT_REQUIRED", "必须指定业务部门", status_code=400)
    return value
