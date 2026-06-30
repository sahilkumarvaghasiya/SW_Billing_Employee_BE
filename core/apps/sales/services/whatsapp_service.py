import os

import requests
from apps.sales.services.pdf_service import generate_bill_pdf
from apps.shops.models import Shop

BILL_SEND_FAILED_MESSAGE = "Bill send failed."


class WhatsAppSendError(Exception):
    def __init__(self, message=BILL_SEND_FAILED_MESSAGE):
        self.user_message = message
        super().__init__(message)


def normalize_indian_phone(phone: str) -> str:
    phone = (
        str(phone)
        .replace(" ", "")
        .replace("+", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    if not phone.startswith("91"):
        phone = f"91{phone}"

    return phone


def _raise_for_meta_response(response, *, context: str):
    print(f"{context} STATUS:", response.status_code)
    print(f"{context} RESPONSE:", response.text)

    if response.ok:
        return

    raise WhatsAppSendError(BILL_SEND_FAILED_MESSAGE)


def upload_pdf_to_meta(pdf_path, shop: Shop):
    url = f"https://graph.facebook.com/v23.0/{shop.whatsapp_phone_number_id}/media"

    headers = {"Authorization": f"Bearer {shop.whatsapp_access_token}"}

    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.split("/")[-1], f, "application/pdf")}

        data = {"messaging_product": "whatsapp", "type": "application/pdf"}

        response = requests.post(url, headers=headers, files=files, data=data)
        _raise_for_meta_response(response, context="UPLOAD")

        return response.json()["id"]


def send_invoice_template_message(
    shop: Shop,
    phone,
    media_id,
    customer_name,
    bill_number,
):
    phone = normalize_indian_phone(phone)

    url = f"https://graph.facebook.com/v25.0/{str(shop.whatsapp_phone_number_id).strip()}/messages"

    headers = {
        "Authorization": f"Bearer {shop.whatsapp_access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": "retail_shop_customer_bill",
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {
                                "id": media_id,
                                "filename": f"Bill-{bill_number}.pdf",
                            },
                        }
                    ],
                },
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": customer_name},
                        {"type": "text", "text": str(bill_number)},
                    ],
                },
            ],
        },
    }

    response = requests.post(url, headers=headers, json=payload)
    _raise_for_meta_response(response, context="SEND")

    return response.json()


def send_bill_via_whatsapp(bill, shop: Shop):
    if not bill.customer or not bill.customer.phone:
        raise WhatsAppSendError("Customer phone is required to send WhatsApp invoice.")

    items = bill.bill_items.select_related(
        "product_variant__product__item_type",
        "product_variant__size",
        "product_variant__color",
    ).order_by("created_at")

    pdf_path = generate_bill_pdf(bill=bill, items=items)

    try:
        media_id = upload_pdf_to_meta(pdf_path, shop)
        customer_name = (bill.customer.name or "Customer").strip() or "Customer"
        return send_invoice_template_message(
            shop=shop,
            phone=bill.customer.phone,
            media_id=media_id,
            customer_name=customer_name,
            bill_number=bill.bill_number,
        )
    except WhatsAppSendError:
        raise
    except Exception:
        raise WhatsAppSendError(BILL_SEND_FAILED_MESSAGE) from None
    finally:
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
