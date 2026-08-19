from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DataSourceType = Literal["mock", "csv", "mes", "erp"]
WorkOrderStatus = Literal["planned", "in_progress", "completed", "cancelled"]
ExceptionSeverity = Literal["low", "medium", "high", "critical"]
ExceptionStatus = Literal["open", "processing", "resolved", "ignored"]
ReportStatus = Literal["draft", "ready", "sent", "failed"]
ProcessStatus = Literal["待生产", "未生产", "生产中", "已完成", "已取消", "已暂停"]


class WorkshopDepartment(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,49}$")
    name: str = Field(min_length=1, max_length=200)
    feishu_chat_id: str = Field(default="", max_length=200)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    enabled: bool = True


class WorkshopProcessRecord(BaseModel):
    """One ERP row: one order may contain multiple process rows."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_record_id: str = Field(min_length=1, max_length=100)
    order_code: str = Field(min_length=1, max_length=100)
    product_order_no: str = Field(min_length=1, max_length=100)
    picking_no: str = Field(default="", max_length=100)
    salesperson: str = Field(default="", max_length=200)
    workshop: str = Field(min_length=1, max_length=200)
    order_date: date
    delivery_date: date
    product_name: str = Field(min_length=1, max_length=300)
    product_quantity: int = Field(ge=0)
    total_meters: float | None = Field(default=None, ge=0)
    total_centimeters: float | None = Field(default=None, ge=0)
    color: str = Field(default="", max_length=300)
    process_department: str = Field(min_length=1, max_length=200)
    process_name: str = Field(min_length=1, max_length=200)
    process_status: ProcessStatus
    reporter_name: str = Field(default="", max_length=200)
    reported_at: datetime | None = None
    completion_rate: float = Field(default=0, ge=0, le=1)
    remark: str = Field(default="", max_length=2000)
    customer_grade: str = Field(default="", max_length=20)
    planned_completion_at: datetime
    owner_name: str = Field(default="", max_length=200)
    submitted_at: datetime
    source_type: DataSourceType = "mock"

    @model_validator(mode="after")
    def validate_process_record(self):
        if self.delivery_date < self.order_date:
            raise ValueError("delivery_date cannot be before order_date")
        if self.process_status == "已完成" and self.completion_rate != 1:
            raise ValueError("completed process must have completion_rate=1")
        if self.reported_at and not self.reporter_name:
            raise ValueError("reporter_name is required when reported_at is set")
        if self.reported_at and self.reported_at < self.submitted_at:
            raise ValueError("reported_at cannot be before submitted_at")
        return self


class WorkshopWorkOrder(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    work_order_no: str = Field(min_length=1, max_length=100)
    department_code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,49}$")
    product_code: str = Field(default="", max_length=100)
    product_name: str = Field(min_length=1, max_length=300)
    planned_quantity: int = Field(ge=0)
    completed_quantity: int = Field(default=0, ge=0)
    planned_start_at: datetime | None = None
    planned_finish_at: datetime
    actual_start_at: datetime | None = None
    actual_finish_at: datetime | None = None
    current_process: str = Field(default="", max_length=200)
    status: WorkOrderStatus = "planned"
    source_type: DataSourceType = "mock"
    source_ref: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_progress_and_dates(self):
        if self.completed_quantity > self.planned_quantity:
            raise ValueError("completed_quantity cannot exceed planned_quantity")
        if self.planned_start_at and self.planned_finish_at < self.planned_start_at:
            raise ValueError("planned_finish_at cannot be before planned_start_at")
        if self.actual_finish_at and not self.actual_start_at:
            raise ValueError("actual_start_at is required when actual_finish_at is set")
        if self.actual_start_at and self.actual_finish_at and self.actual_finish_at < self.actual_start_at:
            raise ValueError("actual_finish_at cannot be before actual_start_at")
        if self.status == "completed" and self.completed_quantity != self.planned_quantity:
            raise ValueError("completed work order must have full planned quantity")
        return self


class WorkshopProductionException(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    exception_no: str = Field(min_length=1, max_length=100)
    department_code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,49}$")
    work_order_no: str | None = Field(default=None, max_length=100)
    exception_type: str = Field(min_length=1, max_length=100)
    severity: ExceptionSeverity = "medium"
    description: str = Field(min_length=1, max_length=5000)
    status: ExceptionStatus = "open"
    occurred_at: datetime
    resolved_at: datetime | None = None
    owner: str = Field(default="", max_length=200)
    source_type: DataSourceType = "mock"
    source_ref: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_resolution(self):
        if self.resolved_at and self.resolved_at < self.occurred_at:
            raise ValueError("resolved_at cannot be before occurred_at")
        if self.status == "resolved" and self.resolved_at is None:
            raise ValueError("resolved_at is required for resolved exception")
        if self.status != "resolved" and self.resolved_at is not None:
            raise ValueError("resolved_at is only allowed for resolved exception")
        return self


class WorkshopDailyReportSnapshot(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    report_date: date
    department_code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,49}$")
    report_type: Literal["daily"] = "daily"
    version: int = Field(default=1, ge=1)
    status: ReportStatus = "draft"
    planned_quantity: int = Field(default=0, ge=0)
    completed_quantity: int = Field(default=0, ge=0)
    completion_rate: float = Field(default=0, ge=0, le=1)
    active_order_count: int = Field(default=0, ge=0)
    completed_order_count: int = Field(default=0, ge=0)
    due_soon_count: int = Field(default=0, ge=0)
    overdue_count: int = Field(default=0, ge=0)
    exception_count: int = Field(default=0, ge=0)
    unresolved_exception_count: int = Field(default=0, ge=0)
    payload_json: dict = Field(default_factory=dict)
    source_type: DataSourceType = "mock"

    @model_validator(mode="after")
    def validate_aggregates(self):
        if self.completed_quantity > self.planned_quantity:
            raise ValueError("completed_quantity cannot exceed planned_quantity")
        expected = 0 if self.planned_quantity == 0 else self.completed_quantity / self.planned_quantity
        if abs(self.completion_rate - expected) > 0.0001:
            raise ValueError("completion_rate must equal completed_quantity / planned_quantity")
        if self.unresolved_exception_count > self.exception_count:
            raise ValueError("unresolved_exception_count cannot exceed exception_count")
        return self
