from django.contrib import admin
from apps.products.models import Product, ProductVariant, Size


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "shop", "created_at")
    search_fields = ("name",)
    list_filter = ("shop",)
    ordering = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "company_name",
        "shop",
        "gender",
        "is_active",
        "created_at",
    )
    search_fields = ("name", "company_name")
    list_filter = ("shop", "gender", "is_active")
    ordering = ("-created_at",)



@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
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
        "product__company_name",
    )
    list_filter = (
        "product__shop",
        "size",
        "is_active",
    )
    ordering = ("-created_at",)
