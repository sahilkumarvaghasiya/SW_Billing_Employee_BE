from django.contrib import admin

from apps.accounts.models import User
from apps.shops.admin_mixins import PublicSchemaAdminMixin


@admin.register(User)
class UserAdmin(PublicSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "username", "email", "role", "shop")
    list_filter = ("role", "shop")

