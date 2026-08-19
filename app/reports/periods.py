from calendar import monthrange
from datetime import date, timedelta

from app.reports.models import ReportPeriod


def resolve_period(period: ReportPeriod, anchor_date: date) -> tuple[date, date]:
    if period == ReportPeriod.DAILY:
        return anchor_date, anchor_date
    if period == ReportPeriod.WEEKLY:
        start = anchor_date - timedelta(days=anchor_date.weekday())
        return start, start + timedelta(days=6)
    start = anchor_date.replace(day=1)
    return start, anchor_date.replace(day=monthrange(anchor_date.year, anchor_date.month)[1])

