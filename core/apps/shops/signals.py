from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.shops.models import Domain, Shop


def build_tenant_domain(schema_name):
    """Domain hostnames must not contain underscores or spaces (RFC 1034/1035)."""
    suffix = getattr(settings, "TENANT_DOMAIN_SUFFIX", "localhost").strip(".")
    host_prefix = schema_name.replace("_", "-").replace(" ", "-")
    return f"{host_prefix}.{suffix}"


@receiver(post_save, sender=Shop)
def create_default_domain(sender, instance, created, **kwargs):
    if not created:
        return

    Domain.objects.get_or_create(
        tenant=instance,
        is_primary=True,
        defaults={"domain": build_tenant_domain(instance.schema_name)},
    )
