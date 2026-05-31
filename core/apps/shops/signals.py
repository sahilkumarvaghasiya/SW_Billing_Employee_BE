from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.shops.models import Domain, Shop


def build_tenant_domain(schema_name):
    suffix = getattr(settings, "TENANT_DOMAIN_SUFFIX", "localhost").strip(".")
    return f"{schema_name}.{suffix}"


@receiver(post_save, sender=Shop)
def create_default_domain(sender, instance, created, **kwargs):
    if not created:
        return

    Domain.objects.get_or_create(
        tenant=instance,
        is_primary=True,
        defaults={"domain": build_tenant_domain(instance.schema_name)},
    )
