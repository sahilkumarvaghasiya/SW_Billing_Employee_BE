from django.contrib import admin
from apps.vendors.models import Vendor, StockEntry



@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
 

@admin.register(StockEntry)
class StockEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor")