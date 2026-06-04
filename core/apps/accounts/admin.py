from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User
from apps.shops.admin_mixins import PublicSchemaAdminMixin


@admin.register(User)
class UserAdmin(PublicSchemaAdminMixin, BaseUserAdmin):
    list_display = ("id", "username", "email", "role", "shop", "is_blocked", "is_active")
    list_filter = ("role", "shop", "is_blocked", "is_active")
    search_fields = ("username", "email")
    ordering = ("-date_joined",)

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "RetailPilot access",
            {
                "description": (
                    "For the manager dashboard: set Role to Manager and pick a Shop. "
                    "For the employee billing app: set Role to Employee and pick a Shop. "
                    "Superuser/Staff below are only for this Django admin site."
                ),
                "fields": (
                    "role",
                    "shop",
                    "is_blocked",
                    "session_active",
                    "token_version",
                    "failed_device_login_count",
                ),
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "password1",
                    "password2",
                    "role",
                    "shop",
                ),
            },
        ),
    )
