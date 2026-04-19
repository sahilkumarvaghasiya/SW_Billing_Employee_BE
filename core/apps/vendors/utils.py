import uuid
from io import BytesIO

from barcode import Code128
from barcode.writer import ImageWriter
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.products.models import Product


def build_barcode_number(shop_id):
    unique_part = uuid.uuid4().hex[:12].upper()
    return f"{shop_id}-{unique_part}"


def generate_1d_barcode_image(barcode_number):
    barcode = Code128(barcode_number, writer=ImageWriter())
    writer_options = {
        "module_width": 0.3,
        "module_height": 18,
        "quiet_zone": 2,
        "font_size": 10,
        "text_distance": 4,
    }

    file_name = f"bar_codes/{barcode_number}.png"
    buffer = BytesIO()
    barcode.write(buffer, options=writer_options)
    content_file = ContentFile(buffer.getvalue())

    return default_storage.save(file_name, content_file)


def normalize_gender(gender):
    normalized = gender.strip().lower()
    gender_map = {
        "boy": Product.GenderChoices.BOY,
        "men": Product.GenderChoices.MEN,
        "girl": Product.GenderChoices.GIRL,
        "women": Product.GenderChoices.WOMEN,
    }
    return gender_map.get(normalized)


def relative_media_path(barcode_url):
    marker = "/media/"
    if marker in barcode_url:
        return barcode_url.split(marker, 1)[1]
    return ""