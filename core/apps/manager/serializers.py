import re

from django.core.validators import FileExtensionValidator
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.products.models import Company, ItemType, ProductVariant
from apps.sales.models import Bill, PaymentConfig
from apps.sales.utils import format_indian_amount


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
