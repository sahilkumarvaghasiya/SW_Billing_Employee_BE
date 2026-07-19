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
                if self.allow_null or not self.required:
                    return None
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
    colour = LookupValueField(required=False, allow_null=True)
    pieces = serializers.IntegerField(min_value=1)
    sellprice = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)


class GenerateBarcodeRequestSerializer(serializers.Serializer):
    company_name = LookupValueField()
    product_type = LookupValueField()
    gender = serializers.ChoiceField(choices=["boy", "girl", "men", "women"])
    item_variants = BarcodeItemVariantSerializer(many=True)

    def validate_item_variants(self, value):
        if not value:
            raise serializers.ValidationError({"item_variants": "At least one item variant is required."})
        return value


class StockProductVariantSerializer(serializers.Serializer):
    # For existing products the FE sends the ProductVariant id to top up.
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    size = LookupValueField(required=False, allow_null=True)
    colour = LookupValueField(required=False, allow_null=True)
    # Quantity is always required (qty to add for existing, qty for new).
    pieces = serializers.IntegerField(min_value=1)
    # Optional for existing products; enforced for new products in StockProductSerializer.
    sellprice = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0.01, required=False, allow_null=True
    )
    purchase_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0.01, required=False, allow_null=True
    )


class StockProductSerializer(serializers.Serializer):
    is_existing = serializers.BooleanField(required=False, default=False)
    company_name = LookupValueField(required=False, allow_null=True)
    product_type = LookupValueField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=["boy", "girl", "men", "women"], required=False, allow_null=True
    )
    barcode_number = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True
    )
    barcode_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    item_variants = StockProductVariantSerializer(many=True)

    def validate_item_variants(self, value):
        if not value:
            raise serializers.ValidationError({"item_variants": "At least one item variant is required."})
        return value

    def validate(self, attrs):
        is_existing = attrs.get("is_existing", False)
        variants = attrs.get("item_variants") or []

        if is_existing:
            for variant in variants:
                if not variant.get("variant_id"):
                    raise serializers.ValidationError(
                        {"variant_id": "variant_id is required for existing products."}
                    )
        else:
            if not attrs.get("product_type"):
                raise serializers.ValidationError({"product_type": "This field is required."})
            if not attrs.get("gender"):
                raise serializers.ValidationError({"gender": "This field is required."})
            if not attrs.get("barcode_number"):
                raise serializers.ValidationError({"barcode_number": "This field is required."})
            for variant in variants:
                if variant.get("size") in (None, ""):
                    raise serializers.ValidationError({"size": "This field is required."})
                if variant.get("sellprice") is None:
                    raise serializers.ValidationError({"sellprice": "This field is required."})
                if variant.get("purchase_price") is None:
                    raise serializers.ValidationError({"purchase_price": "This field is required."})

        return attrs


class VendorStockCreateSerializer(serializers.Serializer):
    vendor_name = serializers.CharField(max_length=255)
    vendor_address=serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(max_length=20, required=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    gst_number = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paymentdeadlinedate = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    products = StockProductSerializer(many=True)

    def validate_products(self, value):
        if not value:
            raise serializers.ValidationError({"products": "At least one product is required."})
        return value

    def validate(self, attrs):
        vendor_name = (attrs.get("vendor_name") or "").strip()
        phone = (attrs.get("phone") or "").strip()
        email = (attrs.get("email") or "").strip().lower() or None
        gst_number = (attrs.get("gst_number") or "").strip() or None
        if not phone:
            raise serializers.ValidationError({"phone": "Phone number is required."})

        attrs["vendor_name"] = vendor_name
        attrs["phone"] = phone
        attrs["email"] = email
        attrs["gst_number"] = gst_number

        if attrs["paid_amount"] > attrs["total_amount"]:
            raise serializers.ValidationError({"paid_amount": "Paid amount cannot exceed total amount."})
        return attrs



class VendorExistingStockCreateSerializer(serializers.Serializer):
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    paymentdeadlinedate = serializers.DateField(required=False, allow_null=True)
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


class VendorValidationSerializer(serializers.Serializer):
    vendor_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    gst_number = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        vendor_name = (attrs.get("vendor_name") or "").strip()
        phone = (attrs.get("phone") or "").strip()
        email = (attrs.get("email") or "").strip().lower() or None
        gst_number = (attrs.get("gst_number") or "").strip() or None

        if not vendor_name:
            raise serializers.ValidationError({"vendor_name": "Vendor name is required."})
        if not phone:
            raise serializers.ValidationError({"phone": "Phone number is required."})

        attrs["vendor_name"] = vendor_name
        attrs["phone"] = phone
        attrs["email"] = email
        attrs["gst_number"] = gst_number
        return attrs


class VendorListSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    vendor_name = serializers.CharField(source="name", read_only=True)
    phone = serializers.CharField(read_only=True)
