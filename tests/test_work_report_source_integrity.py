import json
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.errors import AppError
from app.workshop.card_content import WorkshopWorkReportRecord, build_work_report_summary
from app.workshop.models import WorkshopProcessRecord
from app.workshop.work_report_adapters import JianDaoYunWorkReportAdapter


TZ = ZoneInfo("Asia/Shanghai")


def _report(
    record_id: str,
    order_no: str,
    quantity: float,
    *,
    process_name: str = "激光焊",
    source_form_name: str = "车间工序—报工",
) -> WorkshopWorkReportRecord:
    timestamp = datetime(2026, 8, 18, 12, 0, tzinfo=TZ)
    return WorkshopWorkReportRecord(
        source_record_id=record_id,
        source_form_name=source_form_name,
        product_order_no=order_no,
        workshop="焊接车间",
        order_date=date(2026, 8, 18),
        delivery_date=date(2026, 8, 18),
        product_name="测试产品",
        planned_quantity=quantity,
        completed_quantity=quantity,
        quantity_unit="公分",
        process_name=process_name,
        process_status="已完工",
        report_department="焊接部",
        reporter_name="邱春鸣",
        reported_at=timestamp,
        completion_rate=1,
        submitted_at=timestamp,
        updated_at=timestamp,
    )


def _plan() -> WorkshopProcessRecord:
    timestamp = datetime(2026, 8, 18, 8, 0, tzinfo=TZ)
    return WorkshopProcessRecord(
        source_record_id="plan-1",
        order_code="ORDER-1",
        product_order_no="MATCHED-1",
        workshop="焊接车间",
        order_date=date(2026, 8, 18),
        delivery_date=date(2026, 8, 18),
        product_name="测试产品",
        product_quantity=1,
        total_centimeters=100,
        process_department="焊接部",
        process_name="激光焊",
        process_status="待生产",
        planned_completion_at=timestamp,
        submitted_at=timestamp,
    )


def test_report_quantities_include_rows_unmatched_to_plan() -> None:
    payload = build_work_report_summary(
        [_plan()],
        [_report("report-1", "MATCHED-1", 100), _report("report-2", "UNMATCHED-1", 200)],
        department="焊接部",
        report_date=date(2026, 8, 18),
    )

    assert payload["completed_centimeters"] == 300
    assert payload["top_performers"][0]["completed_centimeters"] == 300
    assert payload["reported_count"] == 2
    assert payload["matched_reported_count"] == 1
    assert payload["matched_report_record_count"] == 1
    assert payload["unmatched_report_record_count"] == 1
    assert "completed_pieces" not in payload
    assert "completed_pieces" not in payload["top_performers"][0]


def test_quality_inspection_is_excluded_and_orders_are_distinct() -> None:
    payload = build_work_report_summary(
        [],
        [
            _report("standard-1", "ORDER-1", 100),
            _report("standard-2", "ORDER-1", 100, process_name="补焊"),
            _report("standard-quality", "ORDER-2", 50, process_name="焊接质检"),
            _report(
                "pick-1", "ORDER-3", 200,
                source_form_name="抽单工序—报工",
            ),
            _report(
                "pick-quality", "ORDER-4", 60,
                process_name="抽单质检", source_form_name="抽单工序—报工",
            ),
        ],
        department="焊接部",
        report_date=date(2026, 8, 18),
    )

    assert payload["report_record_count_before_exclusions"] == 5
    assert payload["excluded_quality_inspection_record_count"] == 2
    assert payload["report_record_count"] == 3
    assert payload["completed_order_count"] == 2
    assert payload["completed_centimeters"] == 400
    assert payload["source_record_breakdown"] == [
        {
            "form_name": "车间工序—报工",
            "raw_record_count": 3,
            "excluded_quality_inspection_record_count": 1,
            "included_record_count": 2,
        },
        {
            "form_name": "抽单工序—报工",
            "raw_record_count": 2,
            "excluded_quality_inspection_record_count": 1,
            "included_record_count": 1,
        },
    ]


def _adapter() -> JianDaoYunWorkReportAdapter:
    field_map = {
        "product_order_no": "order",
        "report_department": "department",
        "process_name": "process",
        "reporter_name": "reporter",
        "reported_at": "reported_at",
        "planned_quantity": "planned",
        "completed_quantity": "completed",
        "completion_rate": "rate",
    }
    settings = SimpleNamespace(
        jiandaoyun_work_report_field_map=json.dumps(field_map),
        app_timezone="Asia/Shanghai",
    )
    return JianDaoYunWorkReportAdapter(settings, client=object())


def test_adapter_does_not_estimate_quantity_from_completion_rate() -> None:
    row = {
        "_id": "source-1",
        "order": "ORDER-1",
        "department": "焊接部",
        "process": "激光焊",
        "reporter": "邱春鸣",
        "reported_at": "2026-08-18T04:00:00.000Z",
        "planned": 100,
        "completed": 0,
        "rate": 0.5,
    }

    record = _adapter()._map_row(row, date(2026, 8, 18))

    assert record.completed_quantity == 0
    assert record.completion_rate == 0.5


def test_adapter_rejects_missing_source_quantity() -> None:
    row = {
        "_id": "source-2",
        "order": "ORDER-2",
        "department": "焊接部",
        "process": "激光焊",
        "reporter": "邱春鸣",
        "reported_at": "2026-08-18T04:00:00.000Z",
        "planned": 100,
        "rate": 0.5,
    }

    with pytest.raises(AppError) as exc_info:
        _adapter()._map_row(row, date(2026, 8, 18))

    assert exc_info.value.code == "WORK_REPORT_COMPLETED_QUANTITY_MISSING"
