
from rest_framework import serializers
from apps.products.models import Color, ItemType, ProductVariant, Size, Company
from apps.sales.utils import format_indian_amount

class ProductVariantListSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    purchase_price = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product_name",
            "company_name",
            "size",
            "color",
            "gender",
            "purchase_price",
            "final_price",
        ]

    def get_gender(self, obj):
        return getattr(obj.product, "gender", None)

    def get_product_name(self, obj):
        item_type = getattr(getattr(obj, "product", None), "item_type", None)
        return getattr(item_type, "name", None)

    def get_company_name(self, obj):
        product = getattr(obj, "product", None)
        company = getattr(product, "company", None)
        return getattr(company, "name", None)

    def get_size(self, obj):
        return getattr(obj.size, "name", None)

    def get_color(self, obj):
        return getattr(obj.color, "name", None) if obj.color else None

    def get_final_price(self, obj):
        return format_indian_amount(obj.final_price())
    
    def get_purchase_price(self, obj):
        return format_indian_amount(obj.original_purchase_price)
    
class ProductVariantDetailSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    purchase_price = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product_name",
            "company_name",
            "gender",
            "size",
            "color",
            "price",
            "purchase_price",
            "discount_percent",
            "discount_amount",
            "final_price",
            "quantity",
            "barcode_number",
            "barcode_image",
            "description",
        ]

    def get_product_name(self, obj):
        item_type = getattr(getattr(obj, "product", None), "item_type", None)
        return getattr(item_type, "name", None)

    def get_company_name(self, obj):
        product = getattr(obj, "product", None)
        company = getattr(product, "company", None)
        return getattr(company, "name", None)

    def get_description(self, obj):
        return getattr(obj.product, "description", None)

    def get_gender(self, obj):
        return getattr(obj.product, "gender", None)

    def get_size(self, obj):
        return getattr(obj.size, "name", None)

    def get_color(self, obj):
        return getattr(obj.color, "name", None) if obj.color else None

    def get_final_price(self, obj):
        return format_indian_amount(obj.final_price())
    
    def get_purchase_price(self, obj):
        return format_indian_amount(obj.original_purchase_price)
    

class SizeDropdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = Size
        fields = ["id", "name", "created_at"]


class ItemTypeDropdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemType
        fields = ["id", "name", "created_at"]


class ColorDropdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ["id", "name", "created_at"]

class BrandDropdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "created_at"]