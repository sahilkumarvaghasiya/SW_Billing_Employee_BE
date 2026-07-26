from django.contrib import admin

from apps.shops.admin_mixins import TenantSchemaAdminMixin
from apps.vendors.models import (
    StockEntry,
    StockEntryTopUp,
    Vendor,
    VendorPayment,
    VendorPaymentAllocation,
)


@admin.register(Vendor)
class VendorAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name")


@admin.register(StockEntry)
class StockEntryAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "vendor", "stk_number", "status")


@admin.register(StockEntryTopUp)
class StockEntryTopUpAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "stock_entry",
        "product_variant",
        "quantity_added",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = ("stock_entry__stk_number",)


class VendorPaymentAllocationInline(admin.TabularInline):
    model = VendorPaymentAllocation
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(VendorPayment)
class VendorPaymentAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "vendor",
        "amount",
        "discount",
        "surcharge",
        "payment_date",
        "created_at",
    )
    list_filter = ("payment_date",)
    search_fields = ("vendor__name", "id")
    readonly_fields = ("created_at", "updated_at")
    inlines = [VendorPaymentAllocationInline]


@admin.register(VendorPaymentAllocation)
class VendorPaymentAllocationAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "payment",
        "stock_entry",
        "applied_amount",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "payment__id",
        "stock_entry__stk_number",
        "payment__vendor__name",
    )
    readonly_fields = ("created_at",)
