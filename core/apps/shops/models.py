from django.db import models
from django.utils.text import slugify
from django_tenants.models import DomainMixin, TenantMixin


class Shop(TenantMixin):
    name = models.CharField(max_length=200)
    employee_limit = models.IntegerField(default=5)
    mobile_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    whatsapp_phone_number_id = models.CharField(max_length=100)
    whatsapp_access_token = models.TextField()
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    auto_create_schema = True
    auto_drop_schema = True

    class Meta:
        verbose_name = "Shop"
        verbose_name_plural = "Shops"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.schema_name:
            base = slugify(self.name)[:50] or "shop"
            base = base.replace("-", "_")
            candidate = base
            suffix = 1
            while Shop.objects.exclude(pk=self.pk).filter(schema_name=candidate).exists():
                suffix += 1
                candidate = f"{base}{suffix}"
            self.schema_name = candidate
        else:
            self.schema_name = self.schema_name.lower().replace("-", "_")
        super().save(*args, **kwargs)


class Domain(DomainMixin):
    pass
