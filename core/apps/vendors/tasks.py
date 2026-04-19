import logging
from datetime import date
from celery import shared_task
from django.conf import settings
from apps.sales.notifications import create_vendor_payment_due_notification
from apps.vendors.models import StockEntry


logger = logging.getLogger(__name__)



@shared_task
def process_vendor_payment_due_alerts(for_date_iso=None):
    """Process vendor payment alerts for the given date.

    If `for_date_iso` is provided (YYYY-MM-DD), alerts are processed for that date.
    Otherwise, today's local date is used.
    """
    target_date = date.fromisoformat(for_date_iso) if for_date_iso else None
    alert_before_days = getattr(settings, "VENDOR_DUE_ALERT_DAYS_BEFORE", 5)

    due_entries = StockEntry.due_alert_entries_for_date(
        target_date=target_date,
        alert_before_days=alert_before_days,
    )

    created_count = 0
    existing_count = 0

    alerts = [
        {
            "stock_entry_id": entry.id,
            "invoice_number": entry.invoice_number,
            "vendor_name": entry.vendor.name,
            "vendor_phone": entry.vendor.phone,
            "shop_id": entry.shop_id,
            "due_date": entry.due_date.isoformat() if entry.due_date else None,
            "notification_created": False,
        }
        for entry in due_entries
    ]

    for alert, entry in zip(alerts, due_entries):
        _notification, is_created = create_vendor_payment_due_notification(entry)
        alert["notification_created"] = is_created
        if is_created:
            created_count += 1
        else:
            existing_count += 1

    logger.info(
        "Vendor due alert task executed for %s: total=%s, created=%s, existing=%s",
        target_date.isoformat() if target_date else "today",
        len(alerts),
        created_count,
        existing_count,
    )

    return {
        "target_date": (target_date.isoformat() if target_date else None),
        "count": len(alerts),
        "created_notifications": created_count,
        "existing_notifications": existing_count,
        "alerts": alerts,
    }