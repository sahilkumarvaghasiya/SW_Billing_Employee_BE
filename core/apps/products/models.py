from django.db import models
from apps.shops.models import Shop
from decimal import Decimal


class Size(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("shop", "name")
        indexes = [
            models.Index(fields=["shop"]),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    class GenderChoices(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'
        UNISEX = 'unisex', 'Unisex'

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=GenderChoices.choices)
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
            models.Index(fields=["is_active"]), 
        ]

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    qr_code_number = models.CharField(max_length=100, unique=True, null=True, blank=True)
    qr_code_image = models.ImageField(upload_to="qr_codes/", null=True, blank=True)
    size = models.ForeignKey(Size, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.CharField(max_length=50, blank=True, null=True)
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
            models.Index(fields=["product"]),
            models.Index(fields=["product", "is_active"]),
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

    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold