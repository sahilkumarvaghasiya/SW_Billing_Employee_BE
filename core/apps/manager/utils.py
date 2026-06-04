from calendar import monthrange
from datetime import date, datetime, timedelta

from django.utils import timezone


def parse_date_range(range_type: str, date_str: str) -> tuple[date, date]:
    range_type = (range_type or "day").lower()
    date_str = (date_str or "").strip()

    if not date_str:
        today = timezone.localdate()
        return today, today

    if range_type == "month":
        anchor = datetime.strptime(f"{date_str[:7]}-01", "%Y-%m-%d").date()
        last_day = monthrange(anchor.year, anchor.month)[1]
        return anchor, date(anchor.year, anchor.month, last_day)

    anchor = datetime.strptime(date_str[:10], "%Y-%m-%d").date()

    if range_type == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)

    return anchor, anchor


def format_inr(amount) -> str:
    value = float(amount or 0)
    return f"₹ {value:,.0f}"
