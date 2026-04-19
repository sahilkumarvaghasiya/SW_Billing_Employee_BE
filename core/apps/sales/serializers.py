from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.products.models import ProductVariant
from apps.sales.models import Bill, BillItem, Customer, PaymentConfig


class BarcodeLookupProductSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.item_type.name")
    size = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product_name",
            "size",
            "final_price",
        ]

    def get_size(self, obj):
        return obj.size.name if obj.size else None

    def get_final_price(self, obj):
        return obj.final_price()


class CustomerLookupSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="name")

    class Meta:
        model = Customer
        fields = [
            "id",
            "phone",
            "customer_name",
            "address",
        ]


class PaymentConfigQRListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PaymentConfig
        fields = ["id", "name", "image_url"]

    def get_image_url(self, obj):
        if not obj.qr_image:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.qr_image.url)
        return obj.qr_image.url


class SalesHistoryListSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    created_time = serializers.SerializerMethodField()

    class Meta:
        model = Bill
        fields = [
            "bill_number",
            "customer_name",
            "created_time",
            "payment_method",
            "phone_number",
        ]

    def get_customer_name(self, obj):
        return obj.customer.name if obj.customer else None

    def get_phone_number(self, obj):
        return obj.customer.phone if obj.customer else None

    def get_created_time(self, obj):
        local_time = timezone.localtime(obj.created_at)
        return local_time.strftime("%b %d, %Y, %I:%M %p")


class SalesHistoryItemDetailSerializer(serializers.ModelSerializer):
    type_name = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = BillItem
        fields = [
            "type_name",
            "quantity",
            "amount",
            "discount",
            "total_amount",
        ]

    def get_type_name(self, obj):
        product = getattr(obj.product_variant, "product", None)
        item_type = getattr(product, "item_type", None)
        return item_type.name if item_type else None

    def get_amount(self, obj):
        return obj.price

    def get_discount(self, obj):
        base_total = (obj.price or Decimal("0.00")) * (obj.quantity or 0)
        if (obj.discount_percent or Decimal("0.00")) > 0:
            return (base_total * obj.discount_percent) / Decimal("100")
        return obj.discount_amount or Decimal("0.00")

    def get_total_amount(self, obj):
        return obj.total_price


class SalesHistoryDetailSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    created_time = serializers.SerializerMethodField()
    discount_rs = serializers.SerializerMethodField()
    items = SalesHistoryItemDetailSerializer(source="bill_items", many=True, read_only=True)

    class Meta:
        model = Bill
        fields = [
            "bill_number",
            "customer_name",
            "phone_number",
            "created_time",
            "payment_method",
            "subtotal",
            "discount_rs",
            "total_amount",
            "items",
        ]

    def get_customer_name(self, obj):
        return obj.customer.name if obj.customer else None

    def get_phone_number(self, obj):
        return obj.customer.phone if obj.customer else None

    def get_created_time(self, obj):
        local_time = timezone.localtime(obj.created_at)
        return local_time.strftime("%b %d, %Y, %I:%M %p")

    def get_discount_rs(self, obj):
        if (obj.discount_percent or Decimal("0.00")) > 0:
            return (obj.subtotal or Decimal("0.00")) * obj.discount_percent / Decimal("100")
        return obj.discount_amount or Decimal("0.00")


class BillItemCreateSerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal("0.00"))
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal("0.00"))

    def validate(self, attrs):
        discount_percent = attrs.get("discount_percent") or Decimal("0.00")
        discount_amount = attrs.get("discount_amount") or Decimal("0.00")

        if discount_percent > 0 and discount_amount > 0:
            raise serializers.ValidationError({"bill_item": ["Provide either discount percent or discount amount for each item, not both."]})
        return attrs


class BillCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20)
    address = serializers.CharField(required=False, allow_blank=True)
    items = BillItemCreateSerializer(many=True)
    bill_discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal("0.00"))
    bill_discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal("0.00"))
    payment_method = serializers.ChoiceField(choices=Bill.PaymentMethod.choices)
    payment_status = serializers.ChoiceField(choices=Bill.PaymentStatus.choices, required=False, default=Bill.PaymentStatus.PAID)
    selected_payment_config_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        request = self.context["request"]
        shop = request.user.shop

        phone = (attrs.get("phone") or "").strip()
        if not phone:
            raise serializers.ValidationError({"phone": ["Phone number is required."]})

        attrs["phone"] = phone
        attrs["customer_name"] = (attrs.get("customer_name") or "").strip()
        attrs["address"] = (attrs.get("address") or "").strip()

        bill_discount_percent = attrs.get("bill_discount_percent") or Decimal("0.00")
        bill_discount_amount = attrs.get("bill_discount_amount") or Decimal("0.00")

        if not attrs.get("items"):
            raise serializers.ValidationError({"items": ["At least one bill item is required."]})

        payment_method = attrs.get("payment_method")
        selected_payment_config_id = attrs.get("selected_payment_config_id")
        if payment_method == Bill.PaymentMethod.QR and not selected_payment_config_id:
            raise serializers.ValidationError(
                {"selected_payment_config_id": ["This field is required when payment_method is qr."]}
            )

        payment_config = None
        if selected_payment_config_id:
            payment_config = PaymentConfig.objects.filter(
                id=selected_payment_config_id,
                shop=shop,
                is_active=True,
            ).first()
            if not payment_config:
                raise serializers.ValidationError(
                    {"selected_payment_config_id": ["Invalid or inactive payment config for this shop."]}
                )

        item_variant_ids = [item["product_variant_id"] for item in attrs["items"]]
        variants = ProductVariant.objects.select_related("product").filter(
            id__in=item_variant_ids,
            product__shop=shop,
            is_active=True,
        )

        variant_map = {variant.id: variant for variant in variants}
        missing_variant_ids = [variant_id for variant_id in item_variant_ids if variant_id not in variant_map]
        if missing_variant_ids:
            raise serializers.ValidationError(
                {"items": [f"Invalid product_variant_id(s) for this shop: {missing_variant_ids}"]}
            )

        subtotal = Decimal("0.00")
        prepared_items = []

        for item in attrs["items"]:
            variant = variant_map[item["product_variant_id"]]
            quantity = item["quantity"]

            if variant.quantity < quantity:
                raise serializers.ValidationError(
                    {
                        "items": [
                            (
                                f"Insufficient stock for variant {variant.id}. "
                                f"Available: {variant.quantity}, requested: {quantity}."
                            )
                        ]
                    }
                )

            price = Decimal(str(variant.final_price()))
            base_total = price * quantity

            item_discount_percent = item.get("discount_percent") or Decimal("0.00")
            item_discount_amount = item.get("discount_amount") or Decimal("0.00")
            if item_discount_percent > 0:
                item_discount = base_total * item_discount_percent / Decimal("100")
            else:
                item_discount = item_discount_amount

            item_discount = min(item_discount, base_total)
            line_total = max(base_total - item_discount, Decimal("0.00"))
            subtotal += line_total

            prepared_items.append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "price": price,
                    "discount_percent": item_discount_percent,
                    "discount_amount": item_discount_amount,
                    "total_price": line_total,
                }
            )

        if bill_discount_percent > 0:
            bill_discount_value = subtotal * bill_discount_percent / Decimal("100")
        else:
            bill_discount_value = bill_discount_amount

        bill_discount_value = min(bill_discount_value, subtotal)
        total_amount = max(subtotal - bill_discount_value, Decimal("0.00"))

        attrs["selected_payment_config"] = payment_config
        attrs["prepared_items"] = prepared_items
        attrs["computed_subtotal"] = subtotal
        attrs["computed_discount_amount"] = bill_discount_value
        attrs["computed_total_amount"] = total_amount
        attrs["computed_paid_amount"] = total_amount
        return attrs