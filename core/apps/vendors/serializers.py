from rest_framework import serializers


class LookupValueField(serializers.Field):
    """Accept either dropdown ID or free-text value."""

    default_error_messages = {
        "invalid": "Invalid value. Use a string, integer, or object with id/text.",
        "blank": "This field may not be blank.",
        "invalid_id": "Dropdown id must be a valid integer.",
    }

    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")

        if isinstance(data, int):
            return data

        if isinstance(data, str):
            value = data.strip()
            if not value:
                self.fail("blank")
            return value

        if isinstance(data, dict):
            if data.get("id") not in (None, ""):
                raw_id = data.get("id")
                try:
                    parsed_id = int(str(raw_id).strip())
                except (TypeError, ValueError):
                    self.fail("invalid_id")
                return {"id": parsed_id}

            text_value = data.get("text")
            if text_value is None:
                text_value = data.get("value", data.get("name"))

            if text_value is None:
                self.fail("invalid")

            value = str(text_value).strip()
            if not value:
                self.fail("blank")

            return {"text": value}

        self.fail("invalid")

    def to_representation(self, value):
        return value


class BarcodeItemVariantSerializer(serializers.Serializer):
    size = LookupValueField()
    colour = LookupValueField()
    pieces = serializers.IntegerField(min_value=1)
    sellprice = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)


class GenerateBarcodeRequestSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    product_type = LookupValueField()
    gender = serializers.ChoiceField(choices=["boy", "girl", "men", "women"])
    item_variants = BarcodeItemVariantSerializer(many=True)

    def validate_item_variants(self, value):
        if not value:
            raise serializers.ValidationError({"item_variants": "At least one item variant is required."})
        return value


class StockProductVariantSerializer(serializers.Serializer):
    size = LookupValueField()
    colour = LookupValueField()
    pieces = serializers.IntegerField(min_value=1)
    sellprice = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)


class StockProductSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    product_type = LookupValueField()
    gender = serializers.ChoiceField(choices=["boy", "girl", "men", "women"])
    barcode_number = serializers.CharField(max_length=100)
    barcode_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    item_variants = StockProductVariantSerializer(many=True)

    def validate_item_variants(self, value):
        if not value:
            raise serializers.ValidationError({"item_variants": "At least one item variant is required."})
        return value


class VendorStockCreateSerializer(serializers.Serializer):
    vendor_name = serializers.CharField(max_length=255)
    vendor_address=serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(max_length=20, required=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    gst_number = serializers.CharField(max_length=50, required=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paymentdeadlinedate = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    products = StockProductSerializer(many=True)

    def validate_products(self, value):
        if not value:
            raise serializers.ValidationError({"products": "At least one product is required."})
        return value

    def validate(self, attrs):
        phone = (attrs.get("phone") or "").strip()
        gst_number = (attrs.get("gst_number") or "").strip()

        if not phone:
            raise serializers.ValidationError({"phone": "Phone number is required."})

        if not gst_number:
            raise serializers.ValidationError({"gst_number": "GST number is required."})

        attrs["phone"] = phone
        attrs["gst_number"] = gst_number

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
            raise serializers.ValidationError({"products": "At least one product is required."})
        return value

    def validate(self, attrs):
        if attrs["paid_amount"] > attrs["total_amount"]:
            raise serializers.ValidationError({"paid_amount": "Paid amount cannot exceed total amount."})
        return attrs


class VendorListSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    vendor_name = serializers.CharField(source="name", read_only=True)
    phone = serializers.CharField(read_only=True)
