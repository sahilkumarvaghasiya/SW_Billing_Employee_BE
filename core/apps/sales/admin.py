from django.contrib import admin
from django import forms
from django.db import models as django_models
from apps.sales.models import Bill, BillItem, Customer, Notification, PaymentConfig, NotificationRead


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"phone",
		"name",
		"shop",
		"is_active",
		"created_at",
	)
	search_fields = ("phone", "name")
	list_filter = ("shop", "is_active")
	ordering = ("-created_at",)


@admin.register(PaymentConfig)
class PaymentConfigAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"name",
		"shop",
		"is_active",
		"created_at",
	)
	search_fields = ("name",)
	list_filter = ("shop", "is_active")
	ordering = ("-created_at",)


class BillItemInline(admin.TabularInline):
	model = BillItem
	extra = 0
	readonly_fields = ("created_at", "updated_at")
	fields = (
		"product_variant",
		"quantity",
		"price",
		"discount_percent",
		"discount_amount",
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
			"discount_amount": forms.TextInput(attrs={"inputmode": "decimal"}),
			"total_amount": forms.TextInput(attrs={"inputmode": "decimal"}),
			"paid_amount": forms.TextInput(attrs={"inputmode": "decimal"}),
		}


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
	form = BillAdminForm
	list_display = (
		"id",
		"bill_number",
		"shop",
		"created_by",
		"customer",
		"payment_method",
		"payment_status",
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
		"shop",
		"payment_method",
		"payment_status",
		"is_active",
	)
	ordering = ("-created_at",)
	inlines = [BillItemInline]


@admin.register(BillItem)
class BillItemAdmin(admin.ModelAdmin):
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
		"product_variant__product__name",
		"product_variant__product__company__name",
	)
	list_filter = (
		"bill__shop",
		"created_at",
	)
	ordering = ("-created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"shop",
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
		"shop",
		"type",
		"priority",
	)
	ordering = ("-created_at",)


@admin.register(NotificationRead)
class NotificationReadAdmin(admin.ModelAdmin):
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
	list_filter = (
		"notification__shop",
	)
	ordering = ("-read_at",)