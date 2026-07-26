from io import BytesIO

from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa


def generate_vendor_report_pdf(
    *,
    title,
    business_name,
    period_label,
    groups,
):
    html = render_to_string(
        "manager/vendor_report.html",
        {
            "title": title,
            "business_name": business_name,
            "period_label": period_label,
            "generated_at": timezone.localtime().strftime("%d-%m-%Y %H:%M"),
            "groups": groups,
        },
    )

    buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=buffer)

    if status.err:
        raise RuntimeError("Failed to generate vendor report PDF.")

    return buffer.getvalue()
