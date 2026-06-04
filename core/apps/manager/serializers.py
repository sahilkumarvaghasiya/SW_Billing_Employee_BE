from rest_framework import serializers

from apps.accounts.models import User
from apps.products.models import ProductVariant
from apps.sales.models import PaymentConfig


class DashboardUserSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(source="username")
    role = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    lastActive = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "email", "role", "status", "lastActive"]

    def get_role(self, obj):
        return "manager" if obj.role == User.Role.MANAGER else "staff"

    def get_status(self, obj):
        if obj.is_blocked or not obj.is_active:
            return "inactive"
        return "active"

    def get_lastActive(self, obj):
        if obj.last_login:
            return timezone_format(obj.last_login)
        return "—"


def timezone_format(dt):
    from django.utils import timezone as tz

    local = tz.localtime(dt)
    return local.strftime("%Y-%m-%d %H:%M")


    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["id"] = str(instance.id)
        return data


class CreateDashboardUserSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=["manager", "staff"])
    password = serializers.CharField(write_only=True, min_length=8, required=False)

    def validate(self, attrs):
        request = self.context["request"]
        shop = request.user.shop
        if attrs["role"] == "staff":
            employee_count = shop.users.filter(role=User.Role.EMPLOYEE).count()
            if employee_count >= shop.employee_limit:
                raise serializers.ValidationError(
                    {"detail": "Employee limit reached for this shop."}
                )
        if User.objects.filter(email__iexact=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "Email already in use."})
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        shop = request.user.shop
        role = (
            User.Role.MANAGER
            if validated_data["role"] == "manager"
            else User.Role.EMPLOYEE
        )
        password = validated_data.get("password") or "ChangeMe123!"
        user = User(
            username=validated_data["name"],
            email=validated_data["email"],
            role=role,
            shop=shop,
        )
        user.set_password(password)
        user.save()
        return user


class UserStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["active", "inactive"])


class PaymentConfigSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PaymentConfig
        fields = ["id", "name", "image_url", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at", "image_url"]

    def get_image_url(self, obj):
        if not obj.qr_image:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.qr_image.url)
        return obj.qr_image.url


class PaymentConfigWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentConfig
        fields = ["name", "qr_image", "is_active"]


class StockItemSerializer(serializers.ModelSerializer):
    sku = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, source="price")
    qty = serializers.IntegerField(source="quantity")
    updatedAt = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "sku",
            "name",
            "brand",
            "category",
            "size",
            "color",
            "price",
            "qty",
            "updatedAt",
        ]

    def get_sku(self, obj):
        return obj.barcode_number or str(obj.id)

    def get_name(self, obj):
        product = getattr(obj, "product", None)
        item_type = getattr(product, "item_type", None)
        return item_type.name.title() if item_type and item_type.name else "Product"

    def get_brand(self, obj):
        product = getattr(obj, "product", None)
        company = getattr(product, "company", None)
        return company.name.title() if company and company.name else "—"

    def get_category(self, obj):
        product = getattr(obj, "product", None)
        gender = getattr(product, "gender", None)
        return gender.title() if gender else "General"

    def get_size(self, obj):
        return obj.size.name.title() if obj.size and obj.size.name else "—"

    def get_color(self, obj):
        return obj.color.name.title() if obj.color and obj.color.name else "—"

    def get_updatedAt(self, obj):
        return timezone_format(obj.updated_at)


class StockUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    brand = serializers.CharField(required=False)
    category = serializers.CharField(required=False)
    size = serializers.CharField(required=False)
    color = serializers.CharField(required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    qty = serializers.IntegerField(required=False)
