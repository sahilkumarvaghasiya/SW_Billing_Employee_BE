from django.db.models import F, Q

from apps.products.models import ProductVariant


UNDER_THRESHOLD_FILTER = Q(quantity=0) | Q(quantity__lte=F("low_stock_threshold"))


def under_threshold_variants():
    return ProductVariant.objects.filter(is_active=True).filter(UNDER_THRESHOLD_FILTER)
