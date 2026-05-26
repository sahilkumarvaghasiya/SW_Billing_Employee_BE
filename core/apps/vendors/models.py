from django.db import models
from datetime import timedelta
from apps.shops.models import Shop
from django.utils import timezone
import uuid


class Vendor(models.Model):
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="vendors"
    )

    name = models.CharField(max_length=255, db_index=True)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "phone"],
                name="unique_vendor_phone_per_shop"
            ),
            models.UniqueConstraint(
                fields=["shop", "gst_number"],
                name="unique_vendor_gst_per_shop"
            ),
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
        PARTIAL = "partial", "Partially Paid"
        PAID = "paid", "Paid"
        UNPAID = "unpaid", "Unpaid"

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

    stk_number = models.CharField(max_length=100, unique=True, db_index=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)
    status = models.CharField(
        max_length=10,
        choices=StatusChoices.choices,
        default=StatusChoices.UNPAID,
        db_index=True
    )
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    is_fully_paid = models.BooleanField(default=False)
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
    
    def generate_stk_number(self):
        today = timezone.now().date()
        date_str = today.strftime("%Y%m%d")
        return f"STK-{self.shop.id}-{date_str}-{uuid.uuid4().hex[:6].upper()}"

    def clean(self):
        if self.total_amount < 0 or self.paid_amount < 0:
            raise ValueError("Amounts cannot be negative")

        if self.paid_amount > self.total_amount:
            raise ValueError("Paid amount cannot exceed total amount")

    def save(self, *args, **kwargs):
        if not self.stk_number:
            self.stk_number = self.generate_stk_number()

        self.full_clean()

        paid = self.paid_amount or 0
        total = self.total_amount or 0

        if paid >= total and total > 0:
            self.status = self.StatusChoices.PAID
            self.is_fully_paid = True
        elif paid > 0:
            self.status = self.StatusChoices.PARTIAL
        else:
            self.status = self.StatusChoices.UNPAID

        super().save(*args, **kwargs)

        if self.is_fully_paid:
            from apps.sales.notifications import mark_vendor_payment_due_notification_resolved
            mark_vendor_payment_due_notification_resolved(self)

    def __str__(self):
        return self.stk_number

    def alert_start_date(self, alert_before_days=5):
        if not self.due_date:
            return None
        return self.due_date - timedelta(days=alert_before_days)

    def alert_first_display_date(self, alert_before_days=5):
        """Return first date when alert should be visible.

        Formula:
            first_display = max(due_date - alert_before_days, entry_date) + 1 day
        """
        if not self.due_date:
            return None

        alert_start = self.alert_start_date(alert_before_days=alert_before_days)
        entry_date = timezone.localtime(self.created_at).date()
        return max(alert_start, entry_date) + timedelta(days=1)

    def should_show_due_alert(self, target_date=None, alert_before_days=5):
        if self.is_fully_paid:
            return False

        if self.status == self.StatusChoices.PAID:
            return False

        if not self.due_date:
            return False

        if target_date is None:
            target_date = timezone.localdate()

        first_display_date = self.alert_first_display_date(alert_before_days=alert_before_days)
        if not first_display_date:
            return False

        return first_display_date <= target_date <= self.due_date

    @classmethod
    def due_alert_entries_for_date(cls, target_date=None, alert_before_days=5):
        if target_date is None:
            target_date = timezone.localdate()

        candidate_entries = cls.objects.select_related("vendor", "shop").filter(
            due_date__isnull=False,
            is_fully_paid=False,
            due_date__gte=target_date,
        )

        return [
            entry
            for entry in candidate_entries
            if entry.should_show_due_alert(
                target_date=target_date,
                alert_before_days=alert_before_days,
            )
        ]