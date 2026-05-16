import os
import requests
from django.template.loader import render_to_string
from django.conf import settings
from xhtml2pdf import pisa


def generate_bill_pdf(bill, items):
    html = render_to_string(
        "invoice.html",
        {
            "bill": bill,
            "items": items,
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
