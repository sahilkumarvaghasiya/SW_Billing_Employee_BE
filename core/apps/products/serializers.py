
from rest_framework import serializers
from apps.products.models import Color, ItemType, ProductVariant, Size


class ProductVariantListSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.item_type.name")
    company_name = serializers.CharField(source="product.company_name")
    size = serializers.CharField(source="size.name", default=None)
    final_price = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product_name",
            "company_name",
            "size",
            "final_price",
        ]

    def get_final_price(self, obj):
        return obj.final_price()
    
class ProductVariantDetailSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.item_type.name")
    company_name = serializers.CharField(source="product.company_name")
    description = serializers.CharField(source="product.description")
    gender = serializers.CharField(source="product.gender")
    size = serializers.CharField(source="size.name", default=None)
    final_price = serializers.SerializerMethodField()

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
            "discount_percent",
            "discount_amount",
            "final_price",
            "quantity",
            "barcode_number",
            "barcode_image",
            "description",
        ]

    def get_final_price(self, obj):
        return obj.final_price()


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