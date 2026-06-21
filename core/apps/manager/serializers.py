import re
from decimal import Decimal

from django.core.validators import FileExtensionValidator
from django.utils import timezone
from rest_framework import serializers

from dateutil.relativedelta import relativedelta

from apps.accounts.models import User
from apps.products.models import Company, ItemType, Product, ProductVariant
from apps.sales.models import Bill, PaymentConfig
from apps.sales.utils import format_indian_amount
from apps.vendors.models import StockEntry


class ManagerEmployeeCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_email(self, value):
        value = (value or "").strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value

    def validate_phone_number(self, value):
        digits = re.sub(r"\D", "", value or "")

        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]

        if len(digits) != 10 or digits[0] not in "6789":
            raise serializers.ValidationError(
                "Enter a valid 10-digit Indian mobile number."
            )
        return digits

    def _generate_password(self, name, phone_number):
        last4 = phone_number[-4:]
        words = name.split()
        if len(words) >= 2:
            base = words[0] + words[1]
        else:
            base = name[:3]
        return f"{base}@{last4}"

    def create(self, validated_data):
        request = self.context["request"]
        manager = request.user
        shop = manager.shop

        employee_count = shop.users.filter(role=User.Role.EMPLOYEE).count()
        if employee_count >= shop.employee_limit:
            raise serializers.ValidationError(
                {"detail": "You cannot create more employees. Limit reached."}
            )

        name = validated_data["name"]
        phone_number = validated_data["phone_number"]
        password = (validated_data.get("password") or "").strip()
        if not password:
            password = self._generate_password(name, phone_number)

        if User.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError(
                {"phone_number": ["This phone number is already in use."]}
            )

        user = User(
            username=name,
            email=validated_data["email"],
            phone_number=phone_number,
            role=User.Role.EMPLOYEE,
            shop=shop,
        )
        user.set_password(password)
        user.save()

        self._generated_password = password
        return user


class ManagerEmployeeListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="username")
    status = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "phone_number",
            "is_active",
            "is_blocked",
            "status",
            "created_at",
        ]

    def get_status(self, obj):
        if obj.is_blocked or not obj.is_active:
            return "inactive"
        return "active"

    def get_created_at(self, obj):
        if not obj.date_joined:
            return None
        local_time = timezone.localtime(obj.date_joined)
        return local_time.strftime("%b %d, %Y, %I:%M %p")


class ManagerEmployeeBlockSerializer(serializers.Serializer):
    is_blocked = serializers.BooleanField()


class ManagerPaymentConfigSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    qr_image = serializers.FileField(
        write_only=True,
        required=False,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["png", "jpg", "jpeg", "webp", "gif", "svg"]
            )
        ],
    )

    class Meta:
        model = PaymentConfig
        fields = [
            "id",
            "name",
            "qr_image",
            "image_url",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("qr_image"):
            raise serializers.ValidationError(
                {"qr_image": ["QR image is required."]}
            )
        return attrs

    def get_image_url(self, obj):
        if not obj.qr_image:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.qr_image.url)
        return obj.qr_image.url


class ManagerBillListSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    created_time = serializers.SerializerMethodField()

    class Meta:
        model = Bill
        fields = [
            "id",
            "bill_number",
            "customer_name",
            "created_by",
            "payment_method",
            "payment_status",
            "total_amount",
            "created_time",
        ]

    def get_customer_name(self, obj):
        return obj.customer.name if obj.customer else None

    def get_created_by(self, obj):
        return obj.created_by.username if obj.created_by else None

    def get_total_amount(self, obj):
        return format_indian_amount(obj.total_amount)

    def get_created_time(self, obj):
        local_time = timezone.localtime(obj.created_at)
        return local_time.strftime("%b %d, %Y, %I:%M %p")


class ManagerBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name"]


class ManagerItemTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemType
        fields = ["id", "name"]


class ManagerStockItemDetailsSerializer(serializers.ModelSerializer):
    item_name = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    purchase_price = serializers.DecimalField(
        source="original_purchase_price",
        max_digits=10,
        decimal_places=2,
    )
    sell_price = serializers.DecimalField(
        source="price",
        max_digits=10,
        decimal_places=2,
    )
    qty = serializers.IntegerField(source="quantity")
    low_stock_limit = serializers.IntegerField(source="low_stock_threshold")
    status = serializers.SerializerMethodField()
    created = serializers.SerializerMethodField()
    updated = serializers.SerializerMethodField()

    _gender_labels = dict(Product.GenderChoices.choices)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "item_name",
            "brand",
            "size",
            "color",
            "gender",
            "purchase_price",
            "sell_price",
            "qty",
            "low_stock_limit",
            "status",
            "created",
            "updated",
        ]

    def get_item_name(self, obj):
        item_type = getattr(getattr(obj, "product", None), "item_type", None)
        name = getattr(item_type, "name", None)
        return name.title() if name else None

    def get_brand(self, obj):
        company = getattr(getattr(obj, "product", None), "company", None)
        name = getattr(company, "name", None)
        return name.title() if name else None

    def get_size(self, obj):
        name = getattr(obj.size, "name", None)
        return name.upper() if name else None

    def get_color(self, obj):
        name = getattr(obj.color, "name", None)
        return name.title() if name else None

    def get_gender(self, obj):
        value = getattr(getattr(obj, "product", None), "gender", None)
        return self._gender_labels.get(value, value)

    def get_status(self, obj):
        if obj.quantity == 0:
            return "out_of_stock"
        if obj.quantity <= obj.low_stock_threshold:
            return "low_stock"
        return "in_stock"

    def get_created(self, obj):
        return timezone.localtime(obj.created_at).strftime("%b %d, %Y, %I:%M %p")

    def get_updated(self, obj):
        return timezone.localtime(obj.updated_at).strftime("%b %d, %Y, %I:%M %p")


class ManagerStockItemUpdateSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
    )
    quantity = serializers.IntegerField(min_value=0, required=False)
    low_stock_threshold = serializers.IntegerField(min_value=0, required=False)

    class Meta:
        model = ProductVariant
        fields = ["price", "quantity", "low_stock_threshold"]

    def validate(self, attrs):
        editable = {"price", "quantity", "low_stock_threshold"}
        if not editable.intersection(attrs):
            raise serializers.ValidationError(
                {"detail": "Provide at least one of: price, quantity, "
                           "low_stock_threshold."}
            )
        return attrs


class ManagerStockThresholdSerializer(serializers.Serializer):
    default_low_stock_limit = serializers.IntegerField(
        min_value=0,
        required=False,
    )
    reset = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if "default_low_stock_limit" not in attrs and not attrs.get("reset"):
            raise serializers.ValidationError(
                {
                    "detail": [
                        "Provide default_low_stock_limit to update the default, "
                        "or set reset=true to revert all products to the default."
                    ]
                }
            )
        return attrs


class ManagerLowStockItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    sku = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    item_type = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product_name",
            "sku",
            "brand",
            "item_type",
            "quantity",
            "low_stock_threshold",
            "stock_status",
        ]

    def get_product_name(self, obj):
        item_type = getattr(getattr(obj, "product", None), "item_type", None)
        return getattr(item_type, "name", None)

    def get_sku(self, obj):
        return obj.barcode_number

    def get_brand(self, obj):
        company = getattr(getattr(obj, "product", None), "company", None)
        return getattr(company, "name", None)

    def get_item_type(self, obj):
        item_type = getattr(getattr(obj, "product", None), "item_type", None)
        return getattr(item_type, "name", None)

    def get_stock_status(self, obj):
        return "out_of_stock" if obj.quantity == 0 else "low_stock"


class ManagerProductSalesTrendQuerySerializer(serializers.Serializer):
    start_date = serializers.DateField(
        required=False,
        input_formats=["%d-%m-%Y"],
        error_messages={"invalid": "Invalid date format. Use DD-MM-YYYY."},
    )
    end_date = serializers.DateField(
        required=False,
        input_formats=["%d-%m-%Y"],
        error_messages={"invalid": "Invalid date format. Use DD-MM-YYYY."},
    )
    gender = serializers.ListField(
        child=serializers.ChoiceField(choices=Product.GenderChoices.choices),
        required=False,
        default=list,
    )
    item_type = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        error_messages={"invalid": "item_type must be a list of integer IDs."},
    )
    sort = serializers.ChoiceField(
        choices=["most_sold", "least_sold"],
        required=False,
        default="most_sold",
    )

    def validate(self, attrs):
        today = timezone.localdate()
        min_start_date = today - relativedelta(years=1)

        start_date = attrs.get("start_date") or min_start_date
        end_date = attrs.get("end_date") or today

        if start_date < min_start_date:
            raise serializers.ValidationError(
                {
                    "start_date": [
                        "Only the last 1 year of data is available. "
                        f"start_date cannot be before "
                        f"{min_start_date.strftime('%d-%m-%Y')}."
                    ]
                }
            )

        if end_date > today:
            raise serializers.ValidationError(
                {"end_date": ["end_date cannot be in the future."]}
            )

        if start_date > end_date:
            raise serializers.ValidationError(
                {"date_range": ["start_date cannot be greater than end_date."]}
            )

        attrs["start_date"] = start_date
        attrs["end_date"] = end_date
        attrs["min_start_date"] = min_start_date
        return attrs


class ManagerProductSalesTrendItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    gender = serializers.SerializerMethodField()
    item_type = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    total_sold = serializers.IntegerField()

    _gender_labels = dict(Product.GenderChoices.choices)

    def get_gender(self, obj):
        value = obj.get("gender")
        return self._gender_labels.get(value, value)

    def get_item_type(self, obj):
        return (obj.get("item_type_name") or "").title() or None

    def get_brand(self, obj):
        return (obj.get("brand_name") or "").title() or None


class ManagerVendorBillSerializer(serializers.ModelSerializer):
    vendor = serializers.SerializerMethodField()
    stk_no = serializers.CharField(source="stk_number")
    bill_date = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    paid = serializers.SerializerMethodField()
    pending = serializers.SerializerMethodField()
    status = serializers.CharField(source="get_status_display")
    due = serializers.SerializerMethodField()
    stock_lines = serializers.SerializerMethodField()

    class Meta:
        model = StockEntry
        fields = [
            "id",
            "due",
            "vendor",
            "stk_no",
            "bill_date",
            "total",
            "paid",
            "pending",
            "status",
            "stock_lines",
        ]

    def get_vendor(self, obj):
        return (obj.vendor.name or "").title() if obj.vendor else None

    def get_bill_date(self, obj):
        return timezone.localtime(obj.created_at).strftime("%Y-%m-%d")

    def get_total(self, obj):
        return format_indian_amount(obj.total_amount or Decimal("0.00"))

    def get_paid(self, obj):
        return format_indian_amount(obj.paid_amount or Decimal("0.00"))

    def get_pending(self, obj):
        pending = (obj.total_amount or Decimal("0.00")) - (
            obj.paid_amount or Decimal("0.00")
        )
        return format_indian_amount(pending)

    def get_due(self, obj):
        if obj.is_fully_paid or obj.status == StockEntry.StatusChoices.PAID:
            return {"label": "Paid", "state": "paid", "days": 0}

        if not obj.due_date:
            return {"label": "No due date", "state": "none", "days": None}

        today = timezone.localdate()
        delta = (obj.due_date - today).days

        if delta < 0:
            return {"label": f"Overdue {abs(delta)}d", "state": "overdue",
                    "days": abs(delta)}
        return {"label": f"Due in {delta}d", "state": "due", "days": delta}

    def get_stock_lines(self, obj):
        return stock_lines_for_entry(obj)


def stock_lines_for_entry(entry):
    """Aggregate product lines entered on a stock entry (item type + brand + qty)."""
    products = {}
    for variant in entry.stock_variants.all():
        product = variant.product
        product_id = product.id
        if product_id not in products:
            item_type_name = product.item_type.name if product.item_type else None
            brand_name = product.company.name if product.company else None
            products[product_id] = {
                "item_type": (item_type_name or "").title() or None,
                "brand": (brand_name or "").title() or None,
                "qty": 0,
            }
        products[product_id]["qty"] += variant.quantity or 0
    return list(products.values())


class ManagerVendorReportBillSerializer(ManagerVendorBillSerializer):
    """Report/PDF serializer — same fields as bill list including stock_lines."""

    class Meta(ManagerVendorBillSerializer.Meta):
        pass


class ManagerVendorBillPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    def validate(self, attrs):
        entry = self.context["entry"]
        amount = attrs["amount"]

        if entry.is_fully_paid or entry.status == StockEntry.StatusChoices.PAID:
            raise serializers.ValidationError(
                {"detail": "This bill is already fully paid."}
            )

        total = entry.total_amount or Decimal("0.00")
        paid = entry.paid_amount or Decimal("0.00")
        pending = total - paid

        if amount > pending:
            raise serializers.ValidationError(
                {
                    "amount": [
                        f"Amount cannot exceed pending balance "
                        f"({format_indian_amount(pending)})."
                    ]
                }
            )

        return attrs