from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.text import capfirst
from django_tenants.utils import tenant_context

from apps.accounts.models import User
from apps.shops.admin_mixins import PublicSchemaAdminMixin


@admin.register(User)
class UserAdmin(PublicSchemaAdminMixin, BaseUserAdmin):
    list_display = (
        "id",
        "username",
        "email",
        "role",
        "shop",
        "is_blocked",
        "is_active",
    )
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

    def get_deleted_objects(self, objs, request):
        """
        User lives in the public schema, but Bill/NotificationRead live in tenant
        schemas. Django's default delete collector would query billing_bills in the
        public schema (where it doesn't exist) and crash for ANY user, manager or
        employee. We build the confirmation list ourselves to avoid that query.
        """
        to_delete = []
        model_count = {}

        for obj in objs:
            to_delete.append([f"{capfirst(User._meta.verbose_name)}: {obj}"])
            if obj.shop_id:
                to_delete.append(
                    [
                        f"  Tenant data in '{obj.shop.schema_name}' "
                        f"(bills, notifications) may reference this user"
                    ]
                )
            model_count[User._meta.verbose_name_plural] = (
                model_count.get(User._meta.verbose_name_plural, 0) + 1
            )

        return to_delete, model_count, set(), []

    def delete_model(self, request, obj):
        self._delete_user(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self._delete_user(request, obj)

    def _delete_user(self, request, user):
        from apps.sales.models import Bill, NotificationRead
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        if user.shop_id:
            with tenant_context(user.shop):
                if Bill.objects.filter(created_by_id=user.pk).exists():
                    messages.error(
                        request,
                        f"Cannot delete '{user.username}': they have created bills "
                        f"in shop '{user.shop.name}'. Reassign or delete those bills first.",
                    )
                    return
                NotificationRead.objects.filter(user_id=user.pk).delete()

        BlacklistedToken.objects.filter(token__user_id=user.pk).delete()
        OutstandingToken.objects.filter(user_id=user.pk).delete()

        user_qs = User.objects.filter(pk=user.pk)
        user_qs._raw_delete(user_qs.db)
