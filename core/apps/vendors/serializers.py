from rest_framework import serializers


class BarcodeItemVariantSerializer(serializers.Serializer):
    size = serializers.CharField(max_length=50)
    colour = serializers.CharField(max_length=50)
    pieces = serializers.IntegerField(min_value=1)
    sellprice = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)


class GenerateBarcodeRequestSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    product_type = serializers.CharField(max_length=100)
    gender = serializers.ChoiceField(choices=["boy", "girl", "men", "women"])
    item_variants = BarcodeItemVariantSerializer(many=True)

    def validate_item_variants(self, value):
        if not value:
            raise serializers.ValidationError("At least one item variant is required.")
        return value


class StockProductVariantSerializer(serializers.Serializer):
    size = serializers.CharField(max_length=50)
    colour = serializers.CharField(max_length=50)
    pieces = serializers.IntegerField(min_value=1)
    sellprice = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)


class StockProductSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    product_type = serializers.CharField(max_length=100)
    gender = serializers.ChoiceField(choices=["boy", "girl", "men", "women"])
    barcode_number = serializers.CharField(max_length=100)
    barcode_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    item_variants = StockProductVariantSerializer(many=True)

    def validate_item_variants(self, value):
        if not value:
            raise serializers.ValidationError("At least one item variant is required.")
        return value


class VendorStockCreateSerializer(serializers.Serializer):
    vendor_name = serializers.CharField(max_length=255)
    vendor_address=serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paymentdeadlinedate = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    products = StockProductSerializer(many=True)

    def validate_products(self, value):
        if not value:
            raise serializers.ValidationError("At least one product is required.")
        return value

    def validate(self, attrs):
        if attrs["paid_amount"] > attrs["total_amount"]:
            raise serializers.ValidationError({"paid_amount": "Paid amount cannot exceed total amount."})
        return attrs



class VendorExistingStockCreateSerializer(serializers.Serializer):
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paymentdeadlinedate = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    products = StockProductSerializer(many=True)

    def validate_products(self, value):
        if not value:
            raise serializers.ValidationError("At least one product is required.")
        return value

    def validate(self, attrs):
        if attrs["paid_amount"] > attrs["total_amount"]:
            raise serializers.ValidationError({"paid_amount": "Paid amount cannot exceed total amount."})
        return attrs


class VendorListSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    vendor_name = serializers.CharField(source="name", read_only=True)
    phone = serializers.CharField(read_only=True)
