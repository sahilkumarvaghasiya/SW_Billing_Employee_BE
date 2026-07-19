from datetime import datetime
from decimal import Decimal
from collections import OrderedDict

from django.db.models import Count, DecimalField, F, Prefetch, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.manager.serializers import ManagerVendorReportBillSerializer
from apps.manager.utils import parse_id_list
from apps.products.models import ProductVariant
from apps.sales.utils import format_indian_amount
from apps.vendors.models import StockEntry


def parse_vendor_report_date_range(params):
    start_date_param = (params.get("start_date") or "").strip()
    end_date_param = (params.get("end_date") or "").strip()

    start_date = None
    end_date = None

    if start_date_param:
        try:
            start_date = datetime.strptime(start_date_param, "%d-%m-%Y").date()
        except ValueError as exc:
            raise ValidationError(
                {"start_date": ["Invalid date format. Use DD-MM-YYYY."]}
            ) from exc

    if end_date_param:
        try:
            end_date = datetime.strptime(end_date_param, "%d-%m-%Y").date()
        except ValueError as exc:
            raise ValidationError(
                {"end_date": ["Invalid date format. Use DD-MM-YYYY."]}
            ) from exc

    if start_date and end_date and start_date > end_date:
        raise ValidationError(
            {"date_range": ["start_date cannot be greater than end_date."]}
        )

    return start_date, end_date


def vendor_report_entries(params):
    vendor_ids = parse_id_list(params, "vendor")
    start_date, end_date = parse_vendor_report_date_range(params)

    queryset = (
        StockEntry.objects.select_related("vendor")
        .prefetch_related(
            Prefetch(
                "stock_variants",
                queryset=ProductVariant.objects.select_related(
                    "product", "product__item_type", "product__company"
                ),
            )
        )
        .order_by("-created_at")
    )

    if vendor_ids:
        queryset = queryset.filter(vendor_id__in=vendor_ids)
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)

    return queryset, start_date, end_date, vendor_ids


def vendor_report_summary(entries):
    agg = entries.aggregate(
        bills=Count("id"),
        total_billed=Coalesce(
            Sum("total_amount"),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        total_paid=Coalesce(
            Sum(Coalesce(F("paid_amount"), Decimal("0.00"))),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    )

    total_billed = agg["total_billed"]
    total_paid = agg["total_paid"]
    total_pending = total_billed - total_paid

    return {
        "bills": agg["bills"],
        "total_billed": format_indian_amount(total_billed),
        "total_paid": format_indian_amount(total_paid),
        "total_pending": format_indian_amount(total_pending),
    }


def vendor_report_bill_rows(entries):
    return ManagerVendorReportBillSerializer(entries, many=True).data


def _format_report_date(value):
    if not value:
        return "-"
    return value.strftime("%d %b %Y")


def vendor_report_payable_groups(entries):
    """Group stock entries by vendor for a Contacts Payable-style PDF."""
    ordered = entries.order_by("vendor__name", "created_at")
    groups = OrderedDict()

    for entry in ordered:
        vendor = entry.vendor
        vendor_key = vendor.pk if vendor else 0
        vendor_name = ((vendor.name if vendor else "") or "Unknown").strip().upper()

        if vendor_key not in groups:
            groups[vendor_key] = {
                "vendor_name": vendor_name,
                "rows": [],
                "_total_amount": Decimal("0.00"),
                "_total_pending": Decimal("0.00"),
            }

        total = entry.total_amount or Decimal("0.00")
        paid = entry.paid_amount or Decimal("0.00")
        pending = total - paid
        bill_date = timezone.localtime(entry.created_at).date()
        stk = (entry.stk_number or "").strip() or "—"

        groups[vendor_key]["rows"].append(
            {
                "date": _format_report_date(bill_date),
                "description": f"Purchase#{stk}",
                "due_date": _format_report_date(entry.due_date),
                "amount": format_indian_amount(total),
                "pending": format_indian_amount(pending),
            }
        )
        groups[vendor_key]["_total_amount"] += total
        groups[vendor_key]["_total_pending"] += pending

    result = []
    for group in groups.values():
        result.append(
            {
                "vendor_name": group["vendor_name"],
                "rows": group["rows"],
                "total_amount": format_indian_amount(group["_total_amount"]),
                "total_pending": format_indian_amount(group["_total_pending"]),
            }
        )
    return result
