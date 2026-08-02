from django.db import models
from datetime import timedelta
from django.utils import timezone
import uuid

from apps.shops.utils import get_current_tenant_id


class Vendor(models.Model):
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
                fields=["phone"],
                name="unique_vendor_phone",
            ),
            models.UniqueConstraint(
                fields=["gst_number"],
                name="unique_vendor_gst",
            ),
        ]
        indexes = [
            models.Index(fields=["name"]),
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
    gst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    is_fully_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vendor"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]
    
    def generate_stk_number(self):
        today = timezone.now().date()
        date_str = today.strftime("%Y%m%d")
        tenant_id = get_current_tenant_id() or "0"
        return f"STK-{tenant_id}-{date_str}-{uuid.uuid4().hex[:6].upper()}"

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

        candidate_entries = cls.objects.select_related("vendor").filter(
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


class StockEntryTopUp(models.Model):
    """Records a top-up of an existing product variant within a stock entry.

    New products are linked to a stock entry directly through
    ProductVariant.stock_entry. Existing products, however, are merged into
    their original variant (quantity increased in place), so this table keeps a
    per-entry record of what was added, letting the stock history show them.
    """

    stock_entry = models.ForeignKey(
        StockEntry,
        on_delete=models.CASCADE,
        related_name="top_ups",
    )
    product_variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.CASCADE,
        related_name="stock_top_ups",
    )
    quantity_added = models.PositiveIntegerField()
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sell_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["stock_entry"]),
            models.Index(fields=["product_variant"]),
        ]

    def __str__(self):
        return f"{self.stock_entry.stk_number} (+{self.quantity_added})"


class VendorPayment(models.Model):
    """One lump-sum payment event against a vendor (may cover many bills)."""

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    surcharge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_date = models.DateField(db_index=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]
        indexes = [
            models.Index(fields=["vendor", "payment_date"]),
        ]

    def __str__(self):
        return f"PAY-{self.id} {self.vendor_id} {self.amount}"


class VendorPaymentAllocation(models.Model):
    """How much of a VendorPayment was applied to one stock entry bill."""

    payment = models.ForeignKey(
        VendorPayment,
        on_delete=models.CASCADE,
        related_name="allocations",
    )
    stock_entry = models.ForeignKey(
        StockEntry,
        on_delete=models.CASCADE,
        related_name="payment_allocations",
    )
    applied_amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["payment"]),
            models.Index(fields=["stock_entry"]),
        ]

    def __str__(self):
        return f"{self.payment_id} → {self.stock_entry_id}: {self.applied_amount}"
