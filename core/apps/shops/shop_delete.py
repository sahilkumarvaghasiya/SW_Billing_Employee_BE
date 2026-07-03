from django.contrib.auth import get_user_model
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from apps.shops.models import Domain

User = get_user_model()


def delete_users_with_tokens(user_qs) -> int:
    """Remove JWT tokens first, then delete users without touching tenant tables."""
    user_ids = list(user_qs.values_list("pk", flat=True))
    if not user_ids:
        return 0

    outstanding_ids = OutstandingToken.objects.filter(
        user_id__in=user_ids
    ).values_list("pk", flat=True)
    BlacklistedToken.objects.filter(token_id__in=outstanding_ids).delete()
    OutstandingToken.objects.filter(user_id__in=user_ids).delete()

    count = user_qs.count()
    user_qs._raw_delete(user_qs.db)
    return count


def delete_shop(shop, *, preserve_superuser_shop_link: bool = True) -> None:
    """
    Drop tenant schema and remove shop users, domains, and the shop row.
    Safe for production when a shop is no longer needed.
    """
    shop_pk = shop.pk

    try:
        shop._drop_schema(force_drop=True)
    except Exception:
        pass

    if preserve_superuser_shop_link:
        User.objects.filter(is_superuser=True, shop_id=shop_pk).update(shop_id=None)

    delete_users_with_tokens(User.objects.filter(shop_id=shop_pk, is_superuser=False))

    domain_qs = Domain.objects.filter(tenant_id=shop_pk)
    domain_qs._raw_delete(domain_qs.db)

    shop_qs = type(shop).objects.filter(pk=shop_pk)
    shop_qs._raw_delete(shop_qs.db)
