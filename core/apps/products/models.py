from django.db import models
from decimal import Decimal
from apps.shops.models import Shop


class NameMixin(models.Model):
    name = models.CharField(max_length=100)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.name = self.name.strip().lower()
        super().save(*args, **kwargs)


class Color(NameMixin):

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "shop"],
                name="unique_color_per_shop"
            )
        ]
        indexes = [
            models.Index(fields=["shop"]),
        ]

    def __str__(self):
        return self.name


class Size(NameMixin):

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "shop"],
                name="unique_size_per_shop"
            )
        ]
        indexes = [
            models.Index(fields=["shop"]),
        ]

    def __str__(self):
        return self.name


class ItemType(NameMixin):

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "shop"],
                name="unique_itemtype_per_shop"
            )
        ]
        indexes = [
            models.Index(fields=["shop"]),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):

    class GenderChoices(models.TextChoices):
        MEN = 'men', 'Men'
        WOMEN = 'women', 'Women'
        BOY = 'boy', 'Boy'
        GIRL = 'girl', 'Girl'

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=GenderChoices.choices)
    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["shop"]),
            models.Index(fields=["shop", "created_at"]),
            models.Index(fields=["name", "company_name"]),
            models.Index(fields=["gender"]),
            models.Index(fields=["item_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants"
    )
    stock_entry = models.ForeignKey(
        "vendors.StockEntry",
        on_delete=models.CASCADE,
        related_name="stock_variants",
    )

    qr_code_number = models.CharField(max_length=100, unique=False, null=True, blank=True)
    qr_code_image = models.ImageField(upload_to="qr_codes/", null=True, blank=True)
    size = models.ForeignKey(Size, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.FloatField(default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product", "size", "color"]),
            models.Index(fields=["stock_entry"]),
            models.Index(fields=["price"]),
            models.Index(fields=["qr_code_number"]),
        ]

    def final_price(self):
        price = self.price

        if self.discount_percent > 0:
            return price - (price * Decimal(self.discount_percent) / Decimal(100))

        if self.discount_amount > 0:
            return price - self.discount_amount

        return price

    def save(self, *args, **kwargs):
        if self.original_price is None:
            self.original_price = self.price
        super().save(*args, **kwargs)

    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold