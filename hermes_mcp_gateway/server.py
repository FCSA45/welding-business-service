"""Read-only MCP tools backed by the existing business services.

This module is deliberately thin: report, permission and knowledge rules stay
in ``app``. Cherry and Hermes only see the stable MCP tool contract.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import date
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from app.business_routing.intents import BusinessIntent
from app.business_routing.models import BusinessRequest, RequestContext
from app.config import get_settings
from app.errors import AppError
from app.knowledge.contracts import KnowledgeSearchRequest
from app.knowledge.service import KnowledgeService
from app.agent_platform.repository import KnowledgeRepository
from app.agent_platform.search import KnowledgeSearchService
from app.db.session import get_session_factory
from app.workshop.report_handler import WorkshopDailyReportHandler
from app.workshop.work_report_handler import WorkshopWorkReportHandler
from app.workshop.mcp_parameters import parse_statistics_date
from app.workshop.access import resolve_department_scope
from app.workshop.adapters import build_workshop_adapter
from app.workshop.work_report_adapters import build_work_report_adapter
from app.workshop.card_content import _to_centimeters, PIECE_UNIT
from app.workshop.wecom_report_artifacts import build_department_artifacts


logger = logging.getLogger("hermes_mcp_gateway")
mcp = FastMCP("车间业务 MCP")

WELDING_DEPARTMENT = "焊接部"
PAINTING_DEPARTMENT = "油漆部"
AGENT_ID = "workshop-agent"
PAINTING_AGENT_ID = "painting-agent"
DEFAULT_TEST_REQUESTER = "cherry-test-user"
DEFAULT_TEST_CHAT = "cherry-test-chat"


class _BearerTokenMiddleware:
    """Protect the optional remote Streamable HTTP transport."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        if not secrets.compare_digest(authorization, f"Bearer {self.token}"):
            response = JSONResponse(
                {"error": "MCP bearer token is required."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _http_values(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _run_streamable_http() -> None:
    import uvicorn

    token = os.getenv("MCP_HTTP_BEARER_TOKEN", "").strip()
    if not token:
        raise SystemExit("MCP_HTTP_BEARER_TOKEN is required for streamable-http.")
    host = os.getenv("MCP_HTTP_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("MCP_HTTP_HOST must be a loopback address.")
    try:
        port = int(os.getenv("MCP_HTTP_PORT", "28181"))
    except ValueError as exc:
        raise SystemExit("MCP_HTTP_PORT must be an integer.") from exc
    if not 1024 <= port <= 65535:
        raise SystemExit("MCP_HTTP_PORT must be between 1024 and 65535.")
    path = os.getenv("MCP_HTTP_PATH", "/mcp").strip()
    allowed_hosts = _http_values("MCP_HTTP_ALLOWED_HOSTS")
    if not path.startswith("/") or path == "/":
        raise SystemExit("MCP_HTTP_PATH must be a non-root path.")
    if not allowed_hosts:
        raise SystemExit("MCP_HTTP_ALLOWED_HOSTS is required behind HTTPS proxy.")
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.settings.streamable_http_path = path
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", *allowed_hosts],
        allowed_origins=_http_values("MCP_HTTP_ALLOWED_ORIGINS"),
    )
    application = _BearerTokenMiddleware(mcp.streamable_http_app(), token)
    uvicorn.run(application, host=host, port=port, log_level=os.getenv("LOG_LEVEL", "info").lower())

_SCOPE_ALIASES = {
    "welding": WELDING_DEPARTMENT,
    "焊接": WELDING_DEPARTMENT,
    "焊接部": WELDING_DEPARTMENT,
    "painting": PAINTING_DEPARTMENT,
    "油漆": PAINTING_DEPARTMENT,
    "油漆部": PAINTING_DEPARTMENT,
}


def _mcp_department_scope() -> str:
    """Resolve the immutable department boundary of this MCP process."""
    raw = str(get_settings().mcp_department_scope or "").strip()
    return _SCOPE_ALIASES.get(raw.lower(), "")


def _require_mcp_department_scope(department: str) -> None:
    scope = _mcp_department_scope()
    if scope == department:
        return
    if not scope:
        raise AppError(
            "MCP_AGENT_SCOPE_REQUIRED",
            "MCP 未绑定部门智能体，已拒绝读取部门业务数据。",
            status_code=403,
        )
    raise AppError(
        "MCP_AGENT_DEPARTMENT_FORBIDDEN",
        f"当前智能体仅允许读取{scope}数据，不能调用{department}工具。",
        status_code=403,
    )


def _department_tool(department: str):
    """Only publish tools that belong to this process's department scope."""
    return mcp.tool() if _mcp_department_scope() == department else lambda function: function


def _identity(requester_id: str, chat_id: str) -> tuple[str, str]:
    settings = get_settings()
    requester = (requester_id or "").strip()
    chat = (chat_id or "").strip()
    if requester or chat:
        return requester, chat
    if str(getattr(settings, "app_env", "")).strip().lower() in {
        "development", "dev", "test", "testing", "local"
    }:
        return DEFAULT_TEST_REQUESTER, DEFAULT_TEST_CHAT
    raise AppError("WORKSHOP_IDENTITY_REQUIRED", "缺少用户或会话身份，无法校验部门权限", status_code=400)


def _context(requester_id: str, chat_id: str) -> RequestContext:
    requester, chat = _identity(requester_id, chat_id)
    return RequestContext(requester_id=requester, chat_id=chat, channel="mcp")


def _authorize_knowledge_access(
    *, department: str, requester_id: str, chat_id: str
) -> RequestContext:
    """Authorize knowledge access before reading private or shared documents."""
    settings = get_settings()
    context = _context(requester_id, chat_id)
    scope = resolve_department_scope(settings, context.requester_id, chat_id=context.chat_id)
    scope.require(department)
    return context


def _report_request(*, intent: str, statistics_date: str | None, department: str) -> BusinessRequest:
    entities: dict[str, str] = {}
    parsed_date = parse_statistics_date(statistics_date)
    if parsed_date is not None:
        entities["statistics_date"] = parsed_date.isoformat()
    else:
        # Both report tools default to yesterday when Cherry omits the date.
        entities["anchor_days_ago"] = "1"
    return BusinessRequest(
        original_query=f"MCP 查询{department}报表",
        rewritten_query=f"MCP 查询{department}报表",
        intent=intent,
        business_module="workshop",
        department=department,
        output_template=(
            "wecom_work_report"
            if intent == BusinessIntent.WORKSHOP_DEPARTMENT_WORK_REPORT
            else "wecom_department_report"
        ),
        confidence=1.0,
        entities=entities,
    )


def _success(result, department: str, *, generate_artifacts: bool = False) -> dict[str, Any]:
    payload = result.payload or {}
    message = result.message
    if generate_artifacts and payload.get("ok", True):
        try:
            xlsx_path, png_path = build_department_artifacts(
                payload, get_settings(), request_id=uuid4().hex
            )
            payload = {
                **payload,
                "artifacts": {
                    "html_path": str(png_path.with_suffix(".html")),
                    "png_path": str(png_path),
                    "xlsx_path": str(xlsx_path),
                    "png_generated": True,
                },
            }
            message = (
                f"{message}\n\n"
                f"> 已生成日报文件：PNG `{png_path}`｜HTML `{png_path.with_suffix('.html')}`｜Excel `{xlsx_path}`"
            )
        except AppError as exc:
            logger.warning("department report artifact generation failed code=%s", exc.code)
            payload = {
                **payload,
                "artifacts": {
                    "png_generated": False,
                    "error_code": exc.code,
                    "message": exc.message,
                },
            }
    if payload.get("report_type") == "work_report":
        payload = _work_report_mcp_payload(payload)
    return {
        "ok": True,
        "department": department,
        "message": message,
        "template": result.template,
        "payload": payload,
    }


def _work_report_mcp_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose unambiguous metric names so an agent cannot mix count units."""
    result = dict(payload)
    result["source_record_count"] = result.pop("report_record_count", 0)
    result["source_record_count_before_exclusions"] = result.pop(
        "report_record_count_before_exclusions", result["source_record_count"]
    )
    result["deduplicated_source_record_count"] = result.pop(
        "deduplicated_report_record_count", 0
    )
    result["distinct_reported_order_process_count"] = result.pop("reported_count", 0)
    result["matched_plan_order_process_count"] = result.pop("matched_reported_count", 0)
    result["completed_order_count"] = result.get("completed_order_count", 0)
    result.pop("completed_count", None)
    result["excluded_quality_inspection_record_count"] = result.get(
        "excluded_quality_inspection_record_count", 0
    )
    data_source = result.get("data_source") or {}
    forms = data_source.get("forms") or [
        {
            "form_name": "车间工序—报工",
            "entry_id": data_source.get("entry_id", ""),
            "completed_quantity_field": data_source.get("completed_quantity_field", ""),
        }
    ]
    result["source_filter"] = {
        "forms": forms,
        "department_field": "报工部门",
        "department_method": "精确等于",
        "department_value": result.get("department"),
        "date_field": "报工时间",
        "date_value": result.get("report_date"),
        "excluded_process_rule": "工序名称包含‘质检’的记录不计入部门报工统计",
        "quantity_rule": "只读取总公分数/总米数字段，统一按公分展示",
        "completed_order_rule": "distinct(产品订单号)",
    }
    result["metric_definitions"] = {
        "source_record_count_before_exclusions": "两个报工表按部门和日期筛选后的原始记录总数",
        "source_record_count": "排除工序名称含质检后的有效报工记录条数",
        "deduplicated_source_record_count": "按简道云记录 ID 去重后的报工记录条数",
        "distinct_reported_order_process_count": "按产品订单号、报工部门、工序名称去重后的订单工序数",
        "matched_plan_order_process_count": "不同订单工序中能够匹配计划表的数量",
        "pending_report_count": "应报工订单工序减去匹配计划工序后的数量",
        "completed_order_count": "有效报工记录中去重后的产品订单号数量",
        "excluded_quality_inspection_record_count": "因工序名称包含质检而排除的原始报工记录数",
        "source_record_breakdown": "按报工表分别列出原始记录数、质检排除数和净报工记录数",
    }
    return result


def _failure(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, AppError):
        return {
            "ok": False,
            "error_code": exc.code,
            "message": exc.message,
        }
    logger.exception("MCP tool failed")
    return {
        "ok": False,
        "error_code": "MCP_TOOL_FAILED",
        "message": "业务查询失败，请稍后重试。",
    }


def _order_detail(department: str, product_order_no: str, requester_id: str, chat_id: str) -> dict[str, Any]:
    if not product_order_no.strip():
        raise AppError("WORKSHOP_ORDER_REQUIRED", "必须提供订单号", status_code=400)
    settings = get_settings()
    context = _context(requester_id, chat_id)
    scope = resolve_department_scope(settings, context.requester_id, chat_id=context.chat_id)
    adapter = build_workshop_adapter(settings)
    records = adapter.fetch_order_records(
        department=scope.require(department), product_order_no=product_order_no, scope=scope
    )
    unfinished = [row for row in records if row.process_status not in {"已完成", "已完工"}]
    first_record = records[0] if records else None
    return {
        "ok": True,
        "department": department,
        "product_order_no": product_order_no,
        "order_code": first_record.order_code if first_record else None,
        "product_name": first_record.product_name if first_record else None,
        "record_count": len(records),
        "unfinished_processes": list(dict.fromkeys(row.process_name for row in unfinished)),
        "rows": [
            {
                "order_code": row.order_code,
                "product_order_no": row.product_order_no,
                "product_name": row.product_name,
                "process_name": row.process_name,
                "process_status": row.process_status,
                "total_centimeters": round(float(row.total_centimeters or 0), 2),
                "customer_grade": row.customer_grade,
                "planned_completion_at": row.planned_completion_at.isoformat(),
                "delivery_date": row.delivery_date.isoformat(),
                "owner_name": row.owner_name,
                "remark": row.remark,
            }
            for row in records
        ],
    }


def _work_detail(
    department: str, *, product_order_no: str, reporter_name: str,
    statistics_date: str | None, requester_id: str, chat_id: str,
) -> dict[str, Any]:
    if not product_order_no.strip() and not reporter_name.strip() and not statistics_date:
        raise AppError("WORK_REPORT_DETAIL_FILTER_REQUIRED", "订单号、报工人员或统计日期至少提供一项", status_code=400)
    settings = get_settings()
    context = _context(requester_id, chat_id)
    scope = resolve_department_scope(settings, context.requester_id, chat_id=context.chat_id)
    report_date = parse_statistics_date(statistics_date) if statistics_date else None
    adapter = build_work_report_adapter(settings)
    records = adapter.fetch_detail(
        department=scope.require(department), product_order_no=product_order_no,
        reporter_name=reporter_name, report_date=report_date, scope=scope,
    )
    excluded_quality_inspection_record_count = sum(
        1 for row in records if "质检" in row.process_name
    )
    records = [row for row in records if "质检" not in row.process_name]
    completed_pieces = round(sum(row.completed_quantity for row in records if row.quantity_unit == PIECE_UNIT), 2)
    source_forms = (
        adapter.source_forms_for(department)
        if hasattr(adapter, "source_forms_for")
        else []
    )
    result = {
        "ok": True,
        "data_source": {
            "form_name": "车间工序—报工",
            "app_id": settings.jiandaoyun_workshop_app_id,
            "entry_id": settings.jiandaoyun_work_report_entry_id,
            "completed_quantity_field": getattr(adapter, "fields", {}).get(
                "completed_quantity", "mock.completed_quantity"
            ),
            "quantity_unit": "公分",
            "strict_source_only": settings.workshop_work_report_adapter == "jiandaoyun_mcp",
            "forms": source_forms,
            "excluded_process_rule": "工序名称包含‘质检’的记录不计入部门报工数据",
        },
        "department": department,
        "product_order_no": product_order_no or None,
        "reporter_name": reporter_name or None,
        "statistics_date": report_date.isoformat() if report_date else None,
        "record_count": len(records),
        "excluded_quality_inspection_record_count": excluded_quality_inspection_record_count,
        "completed_centimeters": round(sum(_to_centimeters(row.completed_quantity, row.quantity_unit) for row in records), 2),
        "rows": [
            {
                "product_order_no": row.product_order_no,
                "process_name": row.process_name,
                "reporter_name": row.reporter_name,
                "reported_at": row.reported_at.isoformat(),
                "completed_quantity": row.completed_quantity,
                "quantity_unit": row.quantity_unit,
                "completion_rate": row.completion_rate,
                "process_status": row.process_status,
                "remark": row.remark,
            }
            for row in records
        ],
    }
    if completed_pieces:
        result["completed_pieces"] = completed_pieces
    return result


@_department_tool(WELDING_DEPARTMENT)
def get_welding_order_daily_report(
    statistics_date: str | None = None,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Query the authorized welding department order daily report."""
    try:
        _require_mcp_department_scope(WELDING_DEPARTMENT)
        result = WorkshopDailyReportHandler(get_settings()).handle(
            _report_request(
                intent=BusinessIntent.WORKSHOP_DEPARTMENT_DAILY_REPORT,
                statistics_date=statistics_date,
                department=WELDING_DEPARTMENT,
            ),
            _context(requester_id, chat_id),
        )
        return _success(result, WELDING_DEPARTMENT, generate_artifacts=True)
    except Exception as exc:
        return _failure(exc)


@_department_tool(WELDING_DEPARTMENT)
def get_welding_work_report(
    statistics_date: str | None = None,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Query the authorized welding department work-report daily summary.

    Work quantities and performer totals are read only from the JianDaoYun
    ``车间工序—报工`` form. The order/process source is used only to calculate
    report coverage, never to discard or estimate work-report quantities.
    """
    try:
        _require_mcp_department_scope(WELDING_DEPARTMENT)
        result = WorkshopWorkReportHandler(get_settings()).handle(
            _report_request(
                intent=BusinessIntent.WORKSHOP_DEPARTMENT_WORK_REPORT,
                statistics_date=statistics_date,
                department=WELDING_DEPARTMENT,
            ),
            _context(requester_id, chat_id),
        )
        return _success(result, WELDING_DEPARTMENT)
    except Exception as exc:
        return _failure(exc)


@_department_tool(WELDING_DEPARTMENT)
def search_welding_knowledge(
    query: str,
    top_k: int = 5,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Search workshop/shared knowledge through the existing backend policy."""
    try:
        _require_mcp_department_scope(WELDING_DEPARTMENT)
        if not get_settings().mcp_knowledge_tools_enabled:
            return {
                "ok": False,
                "error_code": "KNOWLEDGE_BACKEND_DISABLED",
                "message": "当前部署为无数据库 MCP 模式，知识库查询由 Cherry/Hermes 负责。",
            }
        _authorize_knowledge_access(
            department=WELDING_DEPARTMENT,
            requester_id=requester_id,
            chat_id=chat_id,
        )
        cleaned = (query or "").strip()
        if not cleaned:
            return {"ok": False, "error_code": "KNOWLEDGE_QUERY_EMPTY", "message": "请输入要查询的知识问题。"}
        limit = max(1, min(int(top_k), 10))
        session = get_session_factory()()
        try:
            service = KnowledgeService(KnowledgeSearchService(KnowledgeRepository(session)))
            response = service.search(
                KnowledgeSearchRequest(
                    agent_id=AGENT_ID,
                    query=cleaned,
                    domains=["workshop", "shared"],
                    top_k=limit,
                )
            )
            return {
                "ok": True,
                "agent_id": response.agent_id,
                "effective_domains": response.effective_domains,
                "hits": [item.model_dump() for item in response.hits],
            }
        finally:
            session.close()
    except Exception as exc:
        return _failure(exc)


@_department_tool(WELDING_DEPARTMENT)
def get_welding_order_detail(
    product_order_no: str,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Query one authorized welding order and its unfinished processes."""
    try:
        _require_mcp_department_scope(WELDING_DEPARTMENT)
        return _order_detail(WELDING_DEPARTMENT, product_order_no.strip(), requester_id, chat_id)
    except Exception as exc:
        return _failure(exc)


@_department_tool(WELDING_DEPARTMENT)
def get_welding_work_report_detail(
    product_order_no: str = "",
    reporter_name: str = "",
    statistics_date: str | None = None,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Query authorized welding work-report details by order, person, or date."""
    try:
        _require_mcp_department_scope(WELDING_DEPARTMENT)
        return _work_detail(
            WELDING_DEPARTMENT, product_order_no=product_order_no.strip(),
            reporter_name=reporter_name.strip(), statistics_date=statistics_date,
            requester_id=requester_id, chat_id=chat_id,
        )
    except Exception as exc:
        return _failure(exc)


@_department_tool(PAINTING_DEPARTMENT)
def get_painting_order_daily_report(
    statistics_date: str | None = None,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Query the authorized oil-painting department order daily report."""
    try:
        _require_mcp_department_scope(PAINTING_DEPARTMENT)
        result = WorkshopDailyReportHandler(get_settings()).handle(
            _report_request(
                intent=BusinessIntent.WORKSHOP_DEPARTMENT_DAILY_REPORT,
                statistics_date=statistics_date,
                department=PAINTING_DEPARTMENT,
            ),
            _context(requester_id, chat_id),
        )
        return _success(result, PAINTING_DEPARTMENT, generate_artifacts=True)
    except Exception as exc:
        return _failure(exc)


@_department_tool(PAINTING_DEPARTMENT)
def get_painting_work_report(
    statistics_date: str | None = None,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Query the authorized oil-painting department work-report daily summary."""
    try:
        _require_mcp_department_scope(PAINTING_DEPARTMENT)
        result = WorkshopWorkReportHandler(get_settings()).handle(
            _report_request(
                intent=BusinessIntent.WORKSHOP_DEPARTMENT_WORK_REPORT,
                statistics_date=statistics_date,
                department=PAINTING_DEPARTMENT,
            ),
            _context(requester_id, chat_id),
        )
        return _success(result, PAINTING_DEPARTMENT)
    except Exception as exc:
        return _failure(exc)


@_department_tool(PAINTING_DEPARTMENT)
def search_painting_knowledge(
    query: str,
    top_k: int = 5,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Search oil-painting/shared knowledge through the backend policy."""
    try:
        _require_mcp_department_scope(PAINTING_DEPARTMENT)
        if not get_settings().mcp_knowledge_tools_enabled:
            return {
                "ok": False,
                "error_code": "KNOWLEDGE_BACKEND_DISABLED",
                "message": "当前部署为无数据库 MCP 模式，知识库查询由 Cherry/Hermes 负责。",
            }
        _authorize_knowledge_access(
            department=PAINTING_DEPARTMENT,
            requester_id=requester_id,
            chat_id=chat_id,
        )
        cleaned = (query or "").strip()
        if not cleaned:
            return {"ok": False, "error_code": "KNOWLEDGE_QUERY_EMPTY", "message": "请输入要查询的知识问题。"}
        limit = max(1, min(int(top_k), 10))
        session = get_session_factory()()
        try:
            service = KnowledgeService(KnowledgeSearchService(KnowledgeRepository(session)))
            response = service.search(
                KnowledgeSearchRequest(
                    agent_id=PAINTING_AGENT_ID,
                    query=cleaned,
                    domains=["workshop", "shared"],
                    top_k=limit,
                )
            )
            return {
                "ok": True,
                "agent_id": response.agent_id,
                "effective_domains": response.effective_domains,
                "hits": [item.model_dump() for item in response.hits],
            }
        finally:
            session.close()
    except Exception as exc:
        return _failure(exc)


@_department_tool(PAINTING_DEPARTMENT)
def get_painting_order_detail(
    product_order_no: str,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Query one authorized oil-painting order and its unfinished processes."""
    try:
        _require_mcp_department_scope(PAINTING_DEPARTMENT)
        return _order_detail(PAINTING_DEPARTMENT, product_order_no.strip(), requester_id, chat_id)
    except Exception as exc:
        return _failure(exc)


@_department_tool(PAINTING_DEPARTMENT)
def get_painting_work_report_detail(
    product_order_no: str = "",
    reporter_name: str = "",
    statistics_date: str | None = None,
    requester_id: str = "",
    chat_id: str = "",
) -> dict[str, Any]:
    """Query authorized oil-painting work-report details by order, person, or date."""
    try:
        _require_mcp_department_scope(PAINTING_DEPARTMENT)
        return _work_detail(
            PAINTING_DEPARTMENT, product_order_no=product_order_no.strip(),
            reporter_name=reporter_name.strip(), statistics_date=statistics_date,
            requester_id=requester_id, chat_id=chat_id,
        )
    except Exception as exc:
        return _failure(exc)


def main() -> None:
    """Start the stable MCP process entrypoint used by Cherry and Hermes."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower() or "stdio"
    if transport == "streamable-http":
        _run_streamable_http()
        return
    mcp.run(transport)


if __name__ == "__main__":
    main()
