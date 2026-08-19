"""Build matching Excel and PNG artifacts for one WeCom department report."""

from __future__ import annotations

from copy import deepcopy
from contextlib import suppress
from pathlib import Path
import re
from typing import Any

from app.config import Settings
from app.errors import AppError
from app.reports.image_renderer import HtmlToPngRenderer
from app.workshop.outputs.html import render_department_report_html
from app.workshop.outputs.excel import render_department_report_excel
from app.workshop.card_report_html import build_work_report_html
from app.concurrency import semaphore_pool


def _safe_file_part(value: object, fallback: str = "report") -> str:
    part = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or ""))
    return part.strip("._-") or fallback


def build_department_artifacts(
    payload: dict[str, Any], settings: Settings, *, request_id: str
) -> tuple[Path, Path]:
    department = str(payload.get("department") or "车间")
    output_dir = Path(settings.workshop_report_output_dir).resolve() / "wecom"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_request_id = re.sub(r"[^A-Za-z0-9_-]", "", request_id)[:24]
    if not safe_request_id:
        raise AppError("WORKSHOP_REQUEST_ID_INVALID", "车间日报请求编号无效", status_code=422)
    # Duplicate/concurrent WeCom deliveries must never share browser temp files.
    stem = f"{_safe_file_part(department)}-{payload['yesterday_date']}-{safe_request_id}"
    xlsx_path = output_dir / f"{stem}.xlsx"
    png_path = output_dir / f"{stem}.png"
    try:
        with semaphore_pool.get(
            "workshop-excel", getattr(settings, "workshop_excel_max_concurrency", 3)
        ):
            render_department_report_excel(payload, xlsx_path)
    except (OSError, ValueError, TypeError) as exc:
        raise AppError("WORKSHOP_XLSX_BUILD_FAILED", "车间日报 Excel 生成失败", status_code=503) from exc
    if not xlsx_path.is_file() or xlsx_path.stat().st_size == 0:
        raise AppError("WORKSHOP_XLSX_BUILD_FAILED", "车间日报 Excel 生成失败", status_code=503)
    renderer = HtmlToPngRenderer(
        command=settings.report_renderer_command,
        script_path=settings.workshop_report_renderer_script,
        timeout_seconds=settings.workshop_report_image_timeout_seconds,
    )
    html_path = output_dir / f"{stem}.html"
    render_department_report_html(payload, html_path)
    # PNG 是群消息中的摘要图；完整订单保留在 Excel/HTML，避免超长图片渲染失败。
    image_payload = deepcopy(payload)
    limit = int(
        payload.get(
            "example_limit",
            getattr(settings, "workshop_card_item_limit", 5),
        )
    )
    image_payload["delayed_open_orders"] = payload.get("delayed_example_orders", payload["delayed_open_orders"][:limit])
    image_payload["important_orders"] = payload.get("important_example_orders", payload["important_orders"][:limit])
    image_html_path = output_dir / f"{stem}.image.html"
    render_department_report_html(image_payload, image_html_path)
    try:
        with semaphore_pool.get(
            "workshop-png", getattr(settings, "workshop_png_max_concurrency", 1)
        ):
            renderer.render(
                image_html_path.read_text(encoding="utf-8"),
                png_path,
                width=settings.workshop_report_image_width,
            )
    finally:
        with suppress(OSError):
            image_html_path.unlink(missing_ok=True)
    return xlsx_path, png_path


def build_work_report_png(
    payload: dict[str, Any], settings: Settings, *, request_id: str
) -> tuple[Path, Path]:
    """Render the work-report HTML and PNG without sending the HTML itself."""
    department = str(payload.get("department") or "车间")
    output_dir = Path(settings.workshop_report_output_dir).resolve() / "scheduled"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_request_id = re.sub(r"[^A-Za-z0-9_-]", "", request_id)[:24]
    if not safe_request_id:
        raise AppError("WORKSHOP_REQUEST_ID_INVALID", "车间日报请求编号无效", status_code=422)
    stem = f"{_safe_file_part(department)}-{payload['report_date']}-work-{safe_request_id}"
    html_path = output_dir / f"{stem}.html"
    png_path = output_dir / f"{stem}.png"
    html_path.write_text(build_work_report_html(payload), encoding="utf-8")
    renderer = HtmlToPngRenderer(
        command=settings.report_renderer_command,
        script_path=settings.workshop_report_renderer_script,
        timeout_seconds=settings.workshop_report_image_timeout_seconds,
    )
    with semaphore_pool.get(
        "workshop-png", getattr(settings, "workshop_png_max_concurrency", 1)
    ):
        renderer.render(
            html_path.read_text(encoding="utf-8"),
            png_path,
            width=settings.workshop_report_image_width,
        )
    return html_path, png_path


def build_order_report_png(
    payload: dict[str, Any], settings: Settings, *, request_id: str
) -> tuple[Path, Path]:
    """Render the scheduled order-report HTML and PNG without producing Excel."""
    department = str(payload.get("department") or "车间")
    report_date = str(payload.get("yesterday_date") or "unknown")
    output_dir = Path(settings.workshop_report_output_dir).resolve() / "scheduled"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_request_id = re.sub(r"[^A-Za-z0-9_-]", "", request_id)[:24]
    if not safe_request_id:
        raise AppError("WORKSHOP_REQUEST_ID_INVALID", "车间日报请求编号无效", status_code=422)
    stem = f"{_safe_file_part(department)}-{report_date}-order-{safe_request_id}"
    html_path = output_dir / f"{stem}.html"
    png_path = output_dir / f"{stem}.png"
    image_payload = deepcopy(payload)
    image_payload["example_limit"] = min(
        max(1, int(getattr(settings, "workshop_card_item_limit", 5))),
        10,
    )
    render_department_report_html(image_payload, html_path)
    html = html_path.read_text(encoding="utf-8")
    renderer = HtmlToPngRenderer(
        command=settings.report_renderer_command,
        script_path=settings.workshop_report_renderer_script,
        timeout_seconds=settings.workshop_report_image_timeout_seconds,
    )
    with semaphore_pool.get(
        "workshop-png", getattr(settings, "workshop_png_max_concurrency", 1)
    ):
        renderer.render(html, png_path, width=settings.workshop_report_image_width)
    return html_path, png_path
