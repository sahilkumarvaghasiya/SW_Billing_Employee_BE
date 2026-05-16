import requests
from django.conf import settings
from apps.shops.models import Shop



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

def upload_pdf_to_meta(pdf_path, shop: Shop):
    url = f"https://graph.facebook.com/v23.0/{shop.whatsapp_phone_number_id}/media"

    headers = {
        "Authorization": f"Bearer {shop.whatsapp_access_token}"
    }

    with open(pdf_path, "rb") as f:
        files = {
            "file": (pdf_path.split("/")[-1], f, "application/pdf")
        }

        data = {
            "messaging_product": "whatsapp",
            "type": "application/pdf"
        }

        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()

        return response.json()["id"]

# def send_invoice_template_message(
#     phone,
#     media_id,
#     customer_name,
#     bill_number,
# ):
#     url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"
#     headers = {
#         "Authorization": f"Bearer {ACCESS_TOKEN}",
#         "Content-Type": "application/json",
#     }
#     payload = {
#         "messaging_product": "whatsapp",
#         "to": phone,
#         "type": "template",
#         "template": {
#             "name": "hello_world",
#             "language": {"code": "en"},
#             "components": [
#                 {"type": "header", "parameters": [{"type": "document", "document": {"id": media_id, "filename": f"{bill_number}.pdf"}}]},
#                 {"type": "body", "parameters": [{"type": "text", "text": customer_name or "Customer"}, {"type": "text", "text": bill_number}]},
#             ],
#         },
#     }

#     response = requests.post(url, headers=headers, json=payload)
#     response.raise_for_status()
#     return response.json()


def send_invoice_template_message(
    shop: Shop,
    phone,
    media_id,
    customer_name,
    bill_number,
):
    phone = normalize_indian_phone(phone)

    url = f"https://graph.facebook.com/v23.0/{shop.whatsapp_phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {shop.whatsapp_access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"}
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()