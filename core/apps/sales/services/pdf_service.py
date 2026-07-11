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
        # Customer bill always shows item.price:
        #   - no custom / discount%   → price = catalog price
        #   - custom < catalog        → price = catalog price  (discount shown)
        #   - custom > catalog        → price = custom amount  (no discount shown)
        original_rate = _d(item.price)
        net_amount = _d(item.total_price)
        gross_amount = (original_rate * item.quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        discount_amount = max(gross_amount - net_amount, Decimal("0.00"))

        gross_total += gross_amount
        item_discount_total += discount_amount

        line_items.append({
            "item": item,
            "original_rate": original_rate,
            "gross_amount": gross_amount,
            "discount_amount": discount_amount,
            "has_discount": discount_amount > Decimal("0.00"),
            "net_amount": net_amount,
        })

    subtotal = _d(bill.subtotal)
    grand_total = _d(bill.total_amount)
    discount_percent = _d(bill.discount_percent)

    if discount_percent > 0:
        bill_discount = min(
            (subtotal * discount_percent / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            subtotal,
        )
    elif subtotal > grand_total:
        bill_discount = subtotal - grand_total
    else:
        bill_discount = Decimal("0.00")

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
    }


def generate_bill_pdf(bill, items):
    html = render_to_string(
        "invoice.html",
        {
            "bill": bill,
            "items": items,
            "shop": _resolve_shop(bill),
            "inv": build_invoice_context(bill, items),
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
