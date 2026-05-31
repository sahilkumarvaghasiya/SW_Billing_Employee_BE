from django.contrib import admin

from apps.shops.admin_mixins import TenantSchemaAdminMixin
from apps.vendors.models import StockEntry, Vendor


@admin.register(Vendor)
class VendorAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name")


@admin.register(StockEntry)
class StockEntryAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "vendor", "stk_number", "status")
