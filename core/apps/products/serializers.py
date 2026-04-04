
from rest_framework import serializers
from apps.products.models import ProductVariant


class ProductVariantListSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")
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
    product_name = serializers.CharField(source="product.name")
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
            "qr_code_number",
            "qr_code_image",
            "description",
        ]

    def get_final_price(self, obj):
        return obj.final_price()