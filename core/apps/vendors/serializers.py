from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.sales.utils import format_indian_amount
from apps.vendors.models import Vendor, VendorPayment, VendorPaymentAllocation


class LookupValueField(serializers.Field):
    """Accept either dropdown ID or free-text value."""

    default_error_messages = {
        "invalid": "Invalid value. Use a string, integer, or object with id/text.",
        "blank": "This field may not be blank.",
        "invalid_id": "Dropdown id must be a valid integer.",
    }

    def to_internal_value(self, data):
        if data is None:
            if self.allow_null or not self.required:
                return None
            self.fail("blank")

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
                if self.allow_null or not self.required:
                    return None
                self.fail("invalid")

            value = str(text_value).strip()
            if not value:
                if self.allow_null or not self.required:
                    return None
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
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    size = LookupValueField(required=False, allow_null=True)
    colour = LookupValueField(required=False, allow_null=True)
    # Quantity is always required (qty to add for existing, qty for new).
    pieces = serializers.IntegerField(min_value=1)
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
    gst = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=0,
        max_value=100,
        required=False,
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
    gst = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=0,
        max_value=100,
        required=False,
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


class VendorPayableVendorSerializer(serializers.ModelSerializer):
    vendor_id = serializers.IntegerField(source="id", read_only=True)
    vendor_name = serializers.CharField(source="name", read_only=True)
    bills_count = serializers.IntegerField(read_only=True)
    overdue_count = serializers.IntegerField(read_only=True)
    total_pending = serializers.SerializerMethodField()
    is_settled = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            "vendor_id",
            "vendor_name",
            "bills_count",
            "total_pending",
            "overdue_count",
            "is_settled",
        ]

    def get_total_pending(self, obj):
        return format_indian_amount(obj.total_pending or Decimal("0.00"))

    def get_is_settled(self, obj):
        pending = obj.total_pending or Decimal("0.00")
        bills_count = getattr(obj, "bills_count", 0) or 0
        return pending <= 0 or bills_count == 0


class VendorPayableInfoSerializer(serializers.ModelSerializer):
    vendor_id = serializers.IntegerField(source="id", read_only=True)
    vendor_name = serializers.CharField(source="name", read_only=True)
    gst_number = serializers.CharField(read_only=True, allow_null=True)
    total_pending = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            "vendor_id",
            "vendor_name",
            "phone",
            "gst_number",
            "email",
            "address",
            "total_pending",
        ]

    def get_total_pending(self, obj):
        return format_indian_amount(getattr(obj, "total_pending", None) or Decimal("0.00"))


class VendorPayablePaySerializer(serializers.Serializer):
    bill_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=200,
    )
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    discount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        default=Decimal("0.00"),
    )
    surcharge = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        default=Decimal("0.00"),
    )
    payment_date = serializers.DateField(
        required=False,
        allow_null=True,
        input_formats=["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"],
    )

    def validate_bill_ids(self, value):
        seen = set()
        unique = []
        for bill_id in value:
            if bill_id in seen:
                continue
            seen.add(bill_id)
            unique.append(bill_id)
        if not unique:
            raise serializers.ValidationError("Select at least one bill.")
        return unique


class VendorPaymentAllocationSerializer(serializers.ModelSerializer):
    bill_id = serializers.IntegerField(source="stock_entry_id", read_only=True)
    stk_no = serializers.CharField(source="stock_entry.stk_number", read_only=True)
    bill_date = serializers.SerializerMethodField()
    due_date = serializers.SerializerMethodField()
    applied = serializers.SerializerMethodField()

    class Meta:
        model = VendorPaymentAllocation
        fields = ["bill_id", "stk_no", "bill_date", "due_date", "applied"]

    def get_bill_date(self, obj):
        return obj.stock_entry.created_at.strftime("%Y-%m-%d")

    def get_due_date(self, obj):
        if not obj.stock_entry.due_date:
            return None
        return obj.stock_entry.due_date.strftime("%Y-%m-%d")

    def get_applied(self, obj):
        return format_indian_amount(obj.applied_amount)


class VendorPaymentDetailSerializer(serializers.ModelSerializer):
    vendor_id = serializers.IntegerField(source="vendor.id", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    amount = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    surcharge = serializers.SerializerMethodField()
    payment_date = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    allocations = VendorPaymentAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = VendorPayment
        fields = [
            "id",
            "vendor_id",
            "vendor_name",
            "amount",
            "discount",
            "surcharge",
            "payment_date",
            "allocations",
            "created_at",
        ]

    def get_amount(self, obj):
        return format_indian_amount(obj.amount)

    def get_discount(self, obj):
        return format_indian_amount(obj.discount or Decimal("0.00"))

    def get_surcharge(self, obj):
        return format_indian_amount(obj.surcharge or Decimal("0.00"))

    def get_payment_date(self, obj):
        return obj.payment_date.strftime("%d-%m-%Y")

    def get_created_at(self, obj):
        # Asia/Kolkata wall-clock with offset (not UTC).
        return timezone.localtime(obj.created_at).isoformat()
