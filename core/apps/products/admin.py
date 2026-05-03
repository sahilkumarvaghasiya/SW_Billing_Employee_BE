from django.contrib import admin
from apps.products.models import Product, ProductVariant, Size, Company, ItemType, Color


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "shop", "created_at")
    search_fields = ("name",)
    list_filter = ("shop",)
    ordering = ("name",)

@admin.register(ItemType)
class ItemTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "shop", "created_at")
    search_fields = ("name",)
    list_filter = ("shop",)
    ordering = ("name",)

@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "shop", "created_at")
    search_fields = ("name",)
    list_filter = ("shop",)
    ordering = ("name",)
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
        "company",
        "shop",
        "gender",
        "is_active",
        "created_at",
    )
    search_fields = ("name", "company")
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
        "product__company__name",
    )
    list_filter = (
        "product__shop",
        "size",
        "is_active",
    )
    ordering = ("-created_at",)
