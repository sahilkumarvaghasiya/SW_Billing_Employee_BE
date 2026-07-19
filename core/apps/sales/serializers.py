from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from apps.products.models import ProductVariant
from apps.sales.models import Bill, BillItem, Customer, Notification, PaymentConfig
from apps.sales.utils import format_indian_amount


class BarcodeLookupProductSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    quantity = serializers.IntegerField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product_name",
            "size",
            "final_price",
            "quantity",
        ]

    def get_size(self, obj):
        return obj.size.name if obj.size else None

    def get_product_name(self, obj):
        product = getattr(obj, "product", None)
        item_type = getattr(product, "item_type", None)
        return item_type.name if item_type else None

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
            "id",
            "bill_number",
            "customer_name",
            "created_time",
            "payment_method",
            "phone_number",
            "whatsapp_status",
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
    original_amount = serializers.SerializerMethodField()
    final_amount = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = BillItem
        fields = [
            "type_name",
            "quantity",
            "amount",
            "original_amount",
            "final_amount",
            "discount",
            "discount_percent",
            "total_amount",
        ]

    def get_type_name(self, obj):
        product = getattr(obj.product_variant, "product", None)
        item_type = getattr(product, "item_type", None)
        return item_type.name if item_type else None

    def _catalog_unit_price(self, obj):
        return obj.original_price or obj.price or Decimal("0.00")

    def _charged_unit_price(self, obj):
        quantity = obj.quantity or 0
        if quantity > 0:
            return (obj.total_price or Decimal("0.00")) / Decimal(str(quantity))
        return obj.total_price or Decimal("0.00")

    def get_amount(self, obj):
        # Catalog price per unit (before any employee override/discount).
        return format_indian_amount(self._catalog_unit_price(obj))

    def get_original_amount(self, obj):
        return format_indian_amount(self._catalog_unit_price(obj))

    def get_final_amount(self, obj):
        # Per-unit price actually charged.
        return format_indian_amount(self._charged_unit_price(obj))

    def get_discount(self, obj):
        # Discount = catalog total - charged total (0 if item price went up).
        catalog_total = self._catalog_unit_price(obj) * (obj.quantity or 0)
        discount = catalog_total - (obj.total_price or Decimal("0.00"))
        if discount < 0:
            discount = Decimal("0.00")
        return format_indian_amount(discount)

    def get_discount_percent(self, obj):
        return format_indian_amount(obj.discount_percent or Decimal("0.00"))

    def get_total_amount(self, obj):
        return format_indian_amount(obj.total_price)


class SalesHistoryDetailSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    created_time = serializers.SerializerMethodField()
    original_total = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    discount_rs = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    items = SalesHistoryItemDetailSerializer(source="bill_items", many=True, read_only=True)

    class Meta:
        model = Bill
        fields = [
            "bill_number",
            "customer_name",
            "phone_number",
            "created_time",
            "payment_method",
            "whatsapp_status",
            "original_total",
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

    def get_original_total(self, obj):
        # Sum of catalog price × qty — never includes employee overrides above original.
        original_total = Decimal("0.00")
        for item in obj.bill_items.all():
            original_total += (item.original_price or item.price or Decimal("0.00")) * (item.quantity or 0)
        return format_indian_amount(original_total)

    def get_subtotal(self, obj):
        return format_indian_amount(obj.subtotal)

    def get_discount_rs(self, obj):
        if (obj.discount_percent or Decimal("0.00")) > 0:
            discount = (obj.subtotal or Decimal("0.00")) * obj.discount_percent / Decimal("100")
            return format_indian_amount(discount)
        if (obj.custom_amount or Decimal("0.00")) > 0:
            discount = (obj.subtotal or Decimal("0.00")) - (obj.total_amount or Decimal("0.00"))
            if discount < 0:
                discount = Decimal("0.00")
            return format_indian_amount(discount)
        return format_indian_amount(Decimal("0.00"))

    def get_total_amount(self, obj):
        return format_indian_amount(obj.total_amount)


class BillItemCreateSerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    is_return = serializers.BooleanField(required=False, default=False)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal("0.00"))
    custom_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal("0.00"))

    def validate(self, attrs):
        discount_percent = attrs.get("discount_percent") or Decimal("0.00")
        custom_amount = attrs.get("custom_amount") or Decimal("0.00")

        if custom_amount < 0:
            raise serializers.ValidationError({"bill_item": ["Custom amount cannot be negative."]})
        if discount_percent > 0 and custom_amount > 0:
            raise serializers.ValidationError({"bill_item": ["Provide either discount percent or custom amount for each item, not both."]})
        return attrs


class BillCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20)
    address = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    items = BillItemCreateSerializer(many=True)
    bill_discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal("0.00"))
    bill_custom_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal("0.00"))
    payment_method = serializers.ChoiceField(choices=Bill.PaymentMethod.choices)
    payment_status = serializers.ChoiceField(choices=Bill.PaymentStatus.choices, required=False, default=Bill.PaymentStatus.PAID)
    selected_payment_config_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        request = self.context["request"]

        phone = (attrs.get("phone") or "").strip()
        if not phone:
            raise serializers.ValidationError({"phone": ["Phone number is required."]})

        attrs["phone"] = phone
        attrs["customer_name"] = (attrs.get("customer_name") or "").strip()
        attrs["address"] = (attrs.get("address") or "").strip()

        bill_discount_percent = attrs.get("bill_discount_percent") or Decimal("0.00")
        bill_custom_amount = attrs.get("bill_custom_amount") or Decimal("0.00")

        has_return_items = any(item.get("is_return") for item in (attrs.get("items") or []))

        # A negative bill total is only valid when the bill contains return lines
        # (shop refunding the customer). Pure sales must never go negative.
        if bill_custom_amount < 0 and not has_return_items:
            raise serializers.ValidationError({"bill_custom_amount": ["Custom amount cannot be negative."]})
        if bill_discount_percent > 0 and bill_custom_amount > 0:
            raise serializers.ValidationError({"bill_custom_amount": ["Provide either discount percent or custom amount for the bill, not both."]})

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
                is_active=True,
            ).first()
            if not payment_config:
                raise serializers.ValidationError(
                    {"selected_payment_config_id": ["Invalid or inactive payment config."]}
                )

        item_variant_ids = [item["product_variant_id"] for item in attrs["items"]]
        variants = ProductVariant.objects.select_related("product").filter(
            id__in=item_variant_ids,
            is_active=True,
        )

        variant_map = {variant.id: variant for variant in variants}
        missing_variant_ids = [variant_id for variant_id in item_variant_ids if variant_id not in variant_map]
        if missing_variant_ids:
            raise serializers.ValidationError(
                {"items": [f"Invalid product_variant_id(s): {missing_variant_ids}"]}
            )

        subtotal = Decimal("0.00")
        prepared_items = []

        for item in attrs["items"]:
            variant = variant_map[item["product_variant_id"]]
            quantity = item["quantity"]
            is_return = bool(item.get("is_return"))

            # Return lines add stock back, so they don't need availability checks.
            if not is_return and variant.quantity < quantity:
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

            # original_price = catalog price at billing time, never overwritten.
            original_price = Decimal(str(variant.final_price()))
            price = original_price

            item_discount_percent = item.get("discount_percent") or Decimal("0.00")
            item_custom_amount = item.get("custom_amount") or Decimal("0.00")
            if item_custom_amount < 0:
                raise serializers.ValidationError({"items": ["Custom amount cannot be negative."]})

            if item_custom_amount > 0:
                # custom_amount is the per-unit final price.
                # When custom > original, price on the bill becomes custom (e.g. 350 > 300).
                # original_price stays as catalog price (300) for employee reporting.
                if item_custom_amount > original_price:
                    price = item_custom_amount
                line_total = item_custom_amount * quantity
            elif item_discount_percent > 0:
                unit_discount = price * item_discount_percent / Decimal("100")
                unit_discount = min(unit_discount, price)
                unit_after_discount = max(price - unit_discount, Decimal("0.00"))
                line_total = unit_after_discount * quantity
            else:
                line_total = price * quantity

            line_total = line_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Returns are stored as a negative contribution so the bill total
            # nets sales against refunds.
            signed_line_total = -line_total if is_return else line_total
            subtotal += signed_line_total

            prepared_items.append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "is_return": is_return,
                    "original_price": original_price,
                    "price": price,
                    "discount_percent": item_discount_percent,
                    "custom_amount": item_custom_amount,
                    "total_price": signed_line_total,
                }
            )

        # `subtotal` is already net of returns (can be negative or zero).
        if bill_custom_amount != 0:
            # Explicit final total from the client (used for return/exchange bills).
            total_amount = bill_custom_amount
        elif bill_discount_percent > 0 and subtotal > 0:
            bill_discount_value = subtotal * bill_discount_percent / Decimal("100")
            bill_discount_value = min(bill_discount_value, subtotal)
            total_amount = max(subtotal - bill_discount_value, Decimal("0.00"))
        else:
            total_amount = subtotal

        # Only return bills may settle to a non-positive amount.
        if total_amount < 0 and not has_return_items:
            raise serializers.ValidationError(
                {"bill_custom_amount": ["Bill total cannot be negative."]}
            )

        if total_amount > 0:
            settlement_direction = Bill.SettlementDirection.CUSTOMER_TO_SHOP
        elif total_amount < 0:
            settlement_direction = Bill.SettlementDirection.SHOP_TO_CUSTOMER
        else:
            settlement_direction = Bill.SettlementDirection.NONE

        # When the shop pays the customer (or nothing is due) the money goes out
        # in cash; there is no QR/card collection.
        if settlement_direction != Bill.SettlementDirection.CUSTOMER_TO_SHOP:
            attrs["payment_method"] = Bill.PaymentMethod.CASH
            payment_config = None

        attrs["selected_payment_config"] = payment_config
        attrs["prepared_items"] = prepared_items
        attrs["computed_subtotal"] = subtotal
        attrs["computed_total_amount"] = total_amount
        attrs["computed_paid_amount"] = total_amount
        attrs["settlement_direction"] = settlement_direction
        return attrs


class NotificationUnreadSerializer(serializers.ModelSerializer):
    display_date = serializers.SerializerMethodField()
    display_time = serializers.SerializerMethodField()
    type_display = serializers.CharField(
        source="get_type_display",
        read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "type_display",
            "title",
            "message",
            "priority",
            "display_date",
            "display_time",
        ]

    def get_display_date(self, obj):
        local_dt = timezone.localtime(obj.created_at)
        today = timezone.localdate()
        created_date = local_dt.date()

        if created_date == today:
            return "Today"
        if created_date == (today - timedelta(days=1)):
            return "Yesterday"
        return created_date.isoformat()

    def get_display_time(self, obj):
        return timezone.localtime(obj.created_at).strftime("%I:%M %p")