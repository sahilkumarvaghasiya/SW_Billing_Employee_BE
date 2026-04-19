from decimal import Decimal, ROUND_HALF_UP
import uuid
from django.db import models
from django.db.models import Sum
from django.core.validators import MinValueValidator
from django.utils import timezone
from apps.products.models import ProductVariant
from apps.shops.models import Shop
from apps.accounts.models import User


class Customer(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="customers")
    phone = models.CharField(max_length=20)
    name = models.CharField(max_length=120, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shop", "phone"], name="unique_customer_phone_per_shop"),
        ]
        indexes = [
            models.Index(fields=["shop", "phone"]),
        ]

    def save(self, *args, **kwargs):
        if self.phone:
            self.phone = self.phone.strip()
        if self.name:
            self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.phone



class PaymentConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="payment_configs")
    name = models.CharField(max_length=100)
    qr_image = models.ImageField(upload_to="qr_codes/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_payment_configs"
        indexes = [
            models.Index(fields=["shop", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name}"


class Bill(models.Model):

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        QR = "qr", "QR"

    class PaymentStatus(models.TextChoices):
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name="bills")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_bills")
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bills"
    )
    bill_number = models.CharField(max_length=50, unique=True, db_index=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices)
    selected_payment_config = models.ForeignKey(
        PaymentConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bills",
        db_index=True
    )
    payment_config_name = models.CharField(max_length=100, blank=True, null=True)
    payment_config_value = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_bills"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["shop"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.bill_number}"


    def generate_bill_number(self):
        today = timezone.now().date()
        date_str = today.strftime("%Y%m%d")

        count = Bill.objects.filter(
            shop=self.shop,
            created_at__date=today
        ).count() + 1

        return f"{self.shop.id}-{date_str}-{str(count).zfill(3)}"

    @staticmethod
    def _to_money(value):
        if value is None:
            return Decimal("0.00")
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        self.subtotal = self._to_money(self.subtotal)
        self.discount_amount = self._to_money(self.discount_amount)
        self.total_amount = self._to_money(self.total_amount)
        self.paid_amount = self._to_money(self.paid_amount)
        self.discount_percent = Decimal(str(self.discount_percent or Decimal("0.00"))).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        super().save(*args, **kwargs)




class BillItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="bill_items")
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="bill_items"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_bill_items"
        indexes = [
            models.Index(fields=["bill"]),
            models.Index(fields=["product_variant"]),
        ]

    def __str__(self):
        return f"{self.product_variant} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.price = Bill._to_money(self.price)
        self.discount_amount = Bill._to_money(self.discount_amount)
        self.total_price = Bill._to_money(self.total_price)
        self.discount_percent = Decimal(str(self.discount_percent or Decimal("0.00"))).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        super().save(*args, **kwargs)


class Notification(models.Model):
    class Type(models.TextChoices):
        LOW_STOCK = "LOW_STOCK", "Low stock"
        OUT_OF_STOCK = "OUT_OF_STOCK", "Out of stock"
        VENDOR_PAYMENT_DUE = "VENDOR_PAYMENT_DUE", "Vendor payment due"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=30, choices=Type.choices, db_index=True)
    title = models.CharField(max_length=120)
    message = models.TextField()
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    is_read = models.BooleanField(default=False, db_index=True)
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    stock_entry = models.ForeignKey(
        "vendors.StockEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["shop", "is_read", "created_at"]),
            models.Index(fields=["shop", "type", "is_read"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "type", "product_variant"],
                condition=models.Q(is_read=False),
                name="uniq_unread_variant_notification_per_type",
            ),
            models.UniqueConstraint(
                fields=["shop", "type", "stock_entry"],
                condition=models.Q(is_read=False),
                name="uniq_unread_stock_entry_notification_per_type",
            ),
        ]

    def __str__(self):
        return f"{self.get_type_display()} - {self.shop_id}"
