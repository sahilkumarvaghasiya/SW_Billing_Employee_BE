from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from apps.sales.utils import format_indian_amount
from apps.vendors.models import StockEntry, VendorPayment


def generate_vendor_statement_pdf(
    *,
    vendor,
    business_name,
    start_date=None,
    end_date=None,
):
    """
    Generates a bank-statement style PDF for a vendor's purchases & payments.
    """
    # 1. Query transactions within specified date range
    bills_qs = StockEntry.objects.filter(vendor_id=vendor.id)
    payments_qs = VendorPayment.objects.filter(vendor_id=vendor.id).prefetch_related(
        "allocations__stock_entry"
    )

    if start_date:
        bills_qs = bills_qs.filter(created_at__date__gte=start_date)
        payments_qs = payments_qs.filter(payment_date__gte=start_date)
    if end_date:
        bills_qs = bills_qs.filter(created_at__date__lte=end_date)
        payments_qs = payments_qs.filter(payment_date__lte=end_date)

    items = []
    for bill in bills_qs:
        dt = timezone.localtime(bill.created_at)
        items.append({
            "kind": "purchase",
            "sort_at": dt,
            "date": dt.strftime("%d %b %Y"),
            "particulars": f"Purchase #{bill.stk_number}",
            "amount": bill.total_amount or Decimal("0.00"),
        })

    for payment in payments_qs:
        if payment.created_at:
            sort_dt = timezone.localtime(payment.created_at)
        else:
            sort_dt = timezone.make_aware(
                datetime.combine(payment.payment_date, datetime.min.time())
            )

        # Collect bill references
        stk_refs = [
            alloc.stock_entry.stk_number if alloc.stock_entry else "N/A"
            for alloc in payment.allocations.all()
        ]

        # Maximum 3 references per line
        stk_ref_lines = [
            ", ".join(stk_refs[i:i + 3])
            for i in range(0, len(stk_refs), 3)
        ]

        items.append({
            "kind": "payment",
            "sort_at": sort_dt,
            "date": payment.payment_date.strftime("%d %b %Y"),
            "particulars": "Payment Paid",
            "stk_ref_lines": stk_ref_lines,
            "amount": payment.amount or Decimal("0.00"),
        })


    # Sort chronologically ascending (oldest first)
    items.sort(key=lambda x: x["sort_at"])

    # 2. Calculate running balances and totals starting from 0.00
    # Purchase = Credit to vendor (we owe them, balance goes up)
    # Payment  = Debit from vendor (we pay them, balance goes down)
    running_balance = Decimal("0.00")
    total_purchase_val = Decimal("0.00")
    total_payment_val = Decimal("0.00")

    rows = []
    for item in items:
        amt = item["amount"]
        if item["kind"] == "purchase":
            total_purchase_val += amt
            running_balance += amt
            rows.append({
                "kind": "purchase",
                "date": item["date"],
                "particulars": item["particulars"],
                "credit": format_indian_amount(amt),   # purchase = credit (we owe vendor)
                "debit": "",
                "balance": format_indian_amount(running_balance),
            })
        elif item["kind"] == "payment":
            total_payment_val += amt
            running_balance -= amt
            rows.append({
                "kind": "payment",
                "date": item["date"],
                "particulars": item["particulars"],
                "stk_ref_lines": item.get("stk_ref_lines", []),
                "debit": format_indian_amount(amt),
                "credit": "",
                "balance": format_indian_amount(running_balance),
            })


    closing_balance_val = total_purchase_val - total_payment_val

    # Reverse rows so latest entries are at the top and oldest entries are at the bottom
    rows.reverse()

    if start_date and end_date:
        period_label = f"{start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}"
    elif start_date:
        period_label = f"From {start_date.strftime('%d-%m-%Y')}"
    elif end_date:
        period_label = f"Until {end_date.strftime('%d-%m-%Y')}"
    else:
        period_label = "All Time"

    html = render_to_string(
        "manager/vendor_statement.html",
        {
            "title": "Cloth Vendor Statement",
            "business_name": business_name,
            "vendor_name": (vendor.name or "").upper(),
            "vendor_gst": getattr(vendor, "gst_number", None) or "",
            "vendor_phone": getattr(vendor, "phone", None) or "",
            "period_label": period_label,
            "total_purchase": format_indian_amount(total_purchase_val),
            "total_payment": format_indian_amount(total_payment_val),
            "closing_balance": format_indian_amount(closing_balance_val),
            "rows": rows,
            "generated_at": timezone.localtime().strftime("%d-%m-%Y %H:%M"),
        },
    )

    buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=buffer)
    if status.err:
        raise RuntimeError("Failed to generate vendor statement PDF.")

    return buffer.getvalue()
