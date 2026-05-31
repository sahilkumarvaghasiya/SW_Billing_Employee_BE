from django.contrib import admin
from django_tenants.admin import TenantAdminMixin

from apps.shops.admin_mixins import PublicSchemaAdminMixin
from apps.shops.models import Domain, Shop


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 1


@admin.register(Shop)
class ShopAdmin(PublicSchemaAdminMixin, TenantAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "schema_name", "employee_limit")
    search_fields = ("name", "schema_name")
    list_filter = ("employee_limit",)
    inlines = [DomainInline]


@admin.register(Domain)
class DomainAdmin(PublicSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    search_fields = ("domain", "tenant__name")
