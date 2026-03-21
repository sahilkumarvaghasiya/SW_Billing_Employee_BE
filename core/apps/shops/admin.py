from django.contrib import admin
from apps.shops.models import Shop
# Register your models here.

class ShopAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "employee_limit")
    search_fields = ("name",)
    list_filter = ("employee_limit",)

admin.site.register(Shop, ShopAdmin)