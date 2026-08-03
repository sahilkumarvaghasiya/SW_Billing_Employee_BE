from django.db.models import F, Q
from rest_framework.exceptions import ValidationError
from apps.sales.utils import format_indian_amount
from apps.products.models import ProductVariant


UNDER_THRESHOLD_FILTER = Q(quantity=0) | Q(quantity__lte=F("low_stock_threshold"))


def under_threshold_variants():
    return ProductVariant.objects.filter(is_active=True).filter(UNDER_THRESHOLD_FILTER)


def parse_id_list(params, key):
    """Parse repeated and/or comma-separated query params into a list of ints.

    Supports ``?key=1&key=2`` and ``?key=1,2`` (and a mix of both).
    Raises a DRF ValidationError if any value is not a valid integer.
    """
    ids = []
    for raw in params.getlist(key):
        for part in str(raw).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError as exc:
                raise ValidationError(
                    {key: [f"{key} must be a list of integer IDs."]}
                ) from exc
    return ids


def parse_timestamp_ordering(
    params,
    *,
    allowed_fields=("created_at", "updated_at"),
    default_field="created_at",
):
    """Build ``order_by`` fields for created/updated column sorting.

    Default: latest first on ``created_at``, then ``updated_at``.
    Pass ``sort=oldest`` to flip the active column to oldest first.
    The other column follows the same direction as a tiebreaker.
    """
    allowed = set(allowed_fields)
    sort_by = (params.get("sort_by") or default_field).strip()
    sort = (params.get("sort") or "").strip().lower()

    if sort_by not in allowed:
        raise ValidationError(
            {"sort_by": [f"Invalid sort_by. Choose from {sorted(allowed)}."]}
        )

    secondary = "updated_at" if sort_by == "created_at" else "created_at"
    prefix = "" if sort == "oldest" else "-"
    return f"{prefix}{sort_by}", f"{prefix}{secondary}"


def format_adjustment_amount(value):
    """Signed settlement adjustment: surcharge adds, discount subtracts."""
    if not value:
        return "-"
    sign = "+" if value > 0 else "-"
    return f"{sign}{format_indian_amount(abs(value))}"