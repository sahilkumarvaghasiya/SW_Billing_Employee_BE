import os
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import connection
from django.template.loader import render_to_string
from xhtml2pdf import pisa


def _resolve_shop(bill):
    tenant = connection.tenant
    if tenant and getattr(tenant, "schema_name", None) != "public":
        return tenant
    created_by = getattr(bill, "created_by", None)
    if created_by and getattr(created_by, "shop", None):
        return created_by.shop
    return None


def _d(value):
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_invoice_context(bill, items):
    """
    Compute all display values for the customer-facing invoice PDF.

    Per line item:
      original_rate  - catalog price per unit (original_price field)
      qty            - quantity
      gross_amount   - original_rate × qty
      discount_amount- gross_amount − net_amount  (0 when price went UP)
      net_amount     - total_price (what customer actually pays for this line)

    Bill totals:
      gross_total    - sum of all gross_amounts
      item_discount  - sum of all per-line discounts
      subtotal       - bill.subtotal  (= sum of total_price, stored on model)
      bill_discount  - bill-level discount in ₹
      grand_total    - bill.total_amount
    """
    line_items = []
    gross_total = Decimal("0.00")
    item_discount_total = Decimal("0.00")

    for item in items:
        is_return = getattr(item, "is_return", False)
        sign = Decimal("-1") if is_return else Decimal("1")

        original_rate = _d(item.price)
        # total_price is stored signed (negative for returns).
        net_amount = _d(item.total_price)
        gross_amount = (original_rate * item.quantity * sign).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        # Discounts don't apply to returns.
        discount_amount = (
            Decimal("0.00") if is_return else max(gross_amount - net_amount, Decimal("0.00"))
        )

        gross_total += gross_amount
        item_discount_total += discount_amount

        line_items.append({
            "item": item,
            "is_return": is_return,
            "original_rate": original_rate,
            "gross_amount": gross_amount,
            "discount_amount": discount_amount,
            "has_discount": discount_amount > Decimal("0.00"),
            "net_amount": net_amount,
        })

    subtotal = _d(bill.subtotal)
    grand_total = _d(bill.total_amount)
    discount_percent = _d(bill.discount_percent)

    has_returns = any(line["is_return"] for line in line_items)

    if discount_percent > 0 and subtotal > 0:
        bill_discount = min(
            (subtotal * discount_percent / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            subtotal,
        )
    elif not has_returns and subtotal > grand_total:
        bill_discount = subtotal - grand_total
    else:
        bill_discount = Decimal("0.00")

    if grand_total > 0:
        settlement_direction = "customer_to_shop"
    elif grand_total < 0:
        settlement_direction = "shop_to_customer"
    else:
        settlement_direction = "none"

    return {
        "line_items": line_items,
        "gross_total": gross_total,
        "item_discount_total": item_discount_total,
        "has_item_discounts": item_discount_total > Decimal("0.00"),
        "subtotal": subtotal,
        "bill_discount": bill_discount,
        "bill_discount_percent": discount_percent,
        "has_bill_discount": bill_discount > Decimal("0.00"),
        "grand_total": grand_total,
        "has_returns": has_returns,
        "is_refund": grand_total <= 0,
        "settlement_direction": settlement_direction,
        "refund_amount": abs(grand_total),
    }


def generate_bill_pdf(bill, items):
    inv = build_invoice_context(bill, items)
    template_name = "invoice_refund.html" if inv["is_refund"] else "invoice.html"

    html = render_to_string(
        template_name,
        {
            "bill": bill,
            "items": items,
            "shop": _resolve_shop(bill),
            "inv": inv,
        },
    )

    folder = "temp_bills"
    os.makedirs(folder, exist_ok=True)
    pdf_path = os.path.join(folder, f"{bill.bill_number}.pdf")

    with open(pdf_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(
            html,
            dest=pdf_file,
            base_url=settings.MEDIA_ROOT,
        )

    if pisa_status.err:
        raise Exception(f"Failed to generate PDF: {pisa_status.err}")

    return pdf_path
