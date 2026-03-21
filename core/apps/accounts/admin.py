from django.contrib import admin
from apps.accounts.models import User
# Register your models here.

class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "email", "role", "shop")
    list_filter = ("role", "shop")

admin.site.register(User, UserAdmin)

