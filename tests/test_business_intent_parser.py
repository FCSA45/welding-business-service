from app.business_routing.intents import BusinessIntent
from app.business_routing.parser import BusinessIntentParser


def test_department_order_report_without_date_defaults_to_yesterday():
    request = BusinessIntentParser().parse("查询油漆部订单日报")

    assert request.intent == BusinessIntent.WORKSHOP_DEPARTMENT_DAILY_REPORT
    assert request.department == "油漆部"
    assert request.period == "yesterday"
    assert request.entities["anchor_days_ago"] == "1"


def test_explicit_yesterday_stays_on_report_route():
    request = BusinessIntentParser().parse("查询昨日油漆部订单日报")

    assert request.intent == BusinessIntent.WORKSHOP_DEPARTMENT_DAILY_REPORT
    assert request.department == "油漆部"
    assert request.entities["anchor_days_ago"] == "1"
