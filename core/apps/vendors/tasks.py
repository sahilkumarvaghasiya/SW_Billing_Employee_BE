import logging
from datetime import date
from celery import shared_task
from django.conf import settings
from django_tenants.utils import get_tenant_model, tenant_context
from apps.sales.notifications import create_vendor_payment_due_notification
from apps.vendors.models import StockEntry


logger = logging.getLogger(__name__)



@shared_task
def process_vendor_payment_due_alerts(for_date_iso=None):
    target_date = date.fromisoformat(for_date_iso) if for_date_iso else None

    alert_before_days = getattr(
        settings,
        "VENDOR_DUE_ALERT_DAYS_BEFORE",
        5
    )

    Tenant = get_tenant_model()

    for tenant in Tenant.objects.exclude(schema_name="public"):
        with tenant_context(tenant):
            due_entries = StockEntry.due_alert_entries_for_date(
                target_date=target_date,
                alert_before_days=alert_before_days,
            )

            for entry in due_entries:
                create_vendor_payment_due_notification(entry)
