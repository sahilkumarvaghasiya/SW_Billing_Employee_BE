from django import forms
from django.contrib import admin
from django.db import models as django_models

from apps.sales.models import Bill, BillItem, Customer, Notification, NotificationRead, PaymentConfig
from apps.shops.admin_mixins import TenantSchemaAdminMixin


@admin.register(Customer)
class CustomerAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "phone",
        "name",
        "is_active",
        "created_at",
    )
    search_fields = ("phone", "name")
    list_filter = ("is_active",)
    ordering = ("-created_at",)


@admin.register(PaymentConfig)
class PaymentConfigAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "is_active",
        "created_at",
    )
    search_fields = ("name",)
    list_filter = ("is_active",)
    ordering = ("-created_at",)


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "product_variant",
        "quantity",
        "original_price",
        "price",
        "discount_percent",
        "custom_amount",
        "total_price",
        "created_at",
        "updated_at",
    )
    formfield_overrides = {
        django_models.DecimalField: {"widget": forms.TextInput(attrs={"inputmode": "decimal"})},
    }


class BillAdminForm(forms.ModelForm):
    class Meta:
        model = Bill
        fields = "__all__"
        widgets = {
            "subtotal": forms.TextInput(attrs={"inputmode": "decimal"}),
            "discount_percent": forms.TextInput(attrs={"inputmode": "decimal"}),
            "custom_amount": forms.TextInput(attrs={"inputmode": "decimal"}),
            "total_amount": forms.TextInput(attrs={"inputmode": "decimal"}),
            "paid_amount": forms.TextInput(attrs={"inputmode": "decimal"}),
        }


@admin.register(Bill)
class BillAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    form = BillAdminForm
    list_display = (
        "id",
        "bill_number",
        "created_by",
        "customer",
        "payment_method",
        "payment_status",
        "whatsapp_status",
        "total_amount",
        "paid_amount",
        "is_active",
        "created_at",
    )
    search_fields = (
        "bill_number",
        "customer__phone",
        "customer__name",
        "created_by__username",
    )
    list_filter = (
        "payment_method",
        "payment_status",
        "whatsapp_status",
        "is_active",
    )
    ordering = ("-created_at",)
    inlines = [BillItemInline]


@admin.register(BillItem)
class BillItemAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "bill",
        "product_variant",
        "quantity",
        "price",
        "total_price",
        "created_at",
    )
    search_fields = (
        "bill__bill_number",
        "product_variant__barcode_number",
        "product_variant__product__item_type__name",
        "product_variant__product__company__name",
    )
    list_filter = (
        "created_at",
    )
    ordering = ("-created_at",)


@admin.register(Notification)
class NotificationAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "type",
        "priority",
        "product_variant",
        "stock_entry",
        "created_at",
    )
    search_fields = (
        "title",
        "message",
        "stock_entry__stk_number",
    )
    list_filter = (
        "type",
        "priority",
    )
    ordering = ("-created_at",)


@admin.register(NotificationRead)
class NotificationReadAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "notification",
        "user",
        "read_at",
    )
    search_fields = (
        "notification__title",
        "notification__message",
        "user__username",
    )
    ordering = ("-read_at",)
