import os

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


def generate_bill_pdf(bill, items):
    html = render_to_string(
        "invoice.html",
        {
            "bill": bill,
            "items": items,
            "shop": _resolve_shop(bill),
        },
    )

    folder = "temp_bills"
    os.makedirs(folder, exist_ok=True)
    pdf_path = os.path.join(folder, f"{bill.bill_number}.pdf")

    base_url = settings.MEDIA_ROOT

    with open(pdf_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(
            html,
            dest=pdf_file,
            base_url=base_url,
        )

    if pisa_status.err:
        raise Exception(f"Failed to generate PDF: {pisa_status.err}")

    return pdf_path
