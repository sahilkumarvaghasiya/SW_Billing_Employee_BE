from django.contrib import admin

from apps.products.models import Color, Company, ItemType, Product, ProductVariant, Size
from apps.shops.admin_mixins import TenantSchemaAdminMixin


@admin.register(Company)
class CompanyAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(ItemType)
class ItemTypeAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Color)
class ColorAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Size)
class SizeAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Product)
class ProductAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "company",
        "gender",
        "is_active",
        "created_at",
    )
    search_fields = ("name", "company")
    list_filter = ("gender", "is_active")
    ordering = ("-created_at",)


@admin.register(ProductVariant)
class ProductVariantAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "barcode_number",
        "size",
        "price",
        "discount_percent",
        "discount_amount",
        "quantity",
        "is_active",
        "created_at",
    )
    search_fields = (
        "barcode_number",
        "product__name",
        "product__company__name",
    )
    list_filter = (
        "size",
        "is_active",
    )
    ordering = ("-created_at",)
