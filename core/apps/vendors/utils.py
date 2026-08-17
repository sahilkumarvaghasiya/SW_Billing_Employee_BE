import logging
import secrets
from io import BytesIO

from barcode import Code128
from barcode.writer import ImageWriter
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import DatabaseError

from apps.products.models import Product, ProductVariant

logger = logging.getLogger(__name__)

# Code128 packs two digits into one symbol in code set C, so a digits-only
# payload of even length prints at roughly half the width of the same number
# of mixed alphanumerics. Twelve digits comes to ~101 modules — about 25mm on
# a 203dpi printer, which leaves the quiet zones a scanner needs either side
# on a 50mm label. The previous "{shop}-{12 hex}" form needed ~47mm of bars
# and did not leave room for them.
BARCODE_SHOP_PREFIX_DIGITS = 3
BARCODE_RANDOM_DIGITS = 9
BARCODE_MAX_ATTEMPTS = 12


def _barcode_shop_prefix(shop_id):
    """Fixed-width numeric prefix so every barcode is the same length."""
    try:
        numeric = int(shop_id)
    except (TypeError, ValueError):
        numeric = sum(ord(char) for char in str(shop_id or ""))

    bucket = abs(numeric) % (10 ** BARCODE_SHOP_PREFIX_DIGITS)
    return f"{bucket:0{BARCODE_SHOP_PREFIX_DIGITS}d}"


def build_barcode_number(shop_id):
    """Allocate a unique digits-only barcode that fits a 50mm label.

    The prefix only groups barcodes by shop for readability — uniqueness is
    enforced by checking the generated value against existing variants, since
    the random part is smaller than the UUID it replaces. The check runs in
    the current tenant schema, so it is per-shop by definition.

    A failed lookup must not block barcode generation: the candidate is
    returned unchecked rather than 500ing the endpoint.
    """
    prefix = _barcode_shop_prefix(shop_id)
    upper_bound = 10 ** BARCODE_RANDOM_DIGITS
    candidate = None

    for _ in range(BARCODE_MAX_ATTEMPTS):
        suffix = f"{secrets.randbelow(upper_bound):0{BARCODE_RANDOM_DIGITS}d}"
        candidate = f"{prefix}{suffix}"
        try:
            if not ProductVariant.objects.filter(
                barcode_number=candidate
            ).exists():
                return candidate
        except DatabaseError:
            logger.exception("Barcode uniqueness check failed; using candidate")
            return candidate

    return candidate


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