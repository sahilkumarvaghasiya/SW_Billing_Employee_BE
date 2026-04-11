from django.db import models
from django.db.models.functions import Lower
from apps.shops.models import Shop
from django.utils import timezone
from django.db.models import Count

class Vendor(models.Model):
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="vendors"
    )

    name = models.CharField(max_length=255, db_index=True)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "shop",
                name="unique_vendor_per_shop"
            )
        ]
        indexes = [
            models.Index(fields=["shop"]),
            models.Index(fields=["shop", "name"]),
        ]

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class StockEntry(models.Model):

    class StatusChoices(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partially Paid"
        PAID = "paid", "Paid"

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="stock_entries"
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="stock_entries"
    )

    invoice_number = models.CharField(max_length=100, unique=True, db_index=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=10,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
        db_index=True
    )
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["shop"]),
            models.Index(fields=["vendor"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]
    
    def generate_invoice_number(self):
        today = timezone.now().date()
        date_str = today.strftime("%Y%m%d")

        count = StockEntry.objects.filter(
            shop=self.shop,
            created_at__date=today
        ).count() + 1

        return f"INV-{self.shop.id}-{date_str}-{str(count).zfill(3)}"

    def clean(self):
        if self.total_amount < 0 or self.paid_amount < 0:
            raise ValueError("Amounts cannot be negative")

        if self.paid_amount > self.total_amount:
            raise ValueError("Paid amount cannot exceed total amount")

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()

        paid = self.paid_amount or 0
        total = self.total_amount or 0

        if paid >= total and total > 0:
            self.status = self.StatusChoices.PAID
        elif paid > 0:
            self.status = self.StatusChoices.PARTIAL
        else:
            self.status = self.StatusChoices.PENDING

        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number