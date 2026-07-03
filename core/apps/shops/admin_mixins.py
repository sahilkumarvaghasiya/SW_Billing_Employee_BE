from django.contrib import admin
from django.db import connection
from django_tenants.utils import get_public_schema_name


class TenantSchemaAdminMixin:
    """Only allow admin access when a tenant schema is active (not public)."""

    def _is_public_schema(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is not None:
            return tenant.schema_name == get_public_schema_name()
        from django.db import connection
        return connection.schema_name == get_public_schema_name()

    def has_module_permission(self, request):
        return not self._is_public_schema(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return not self._is_public_schema(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return not self._is_public_schema(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return not self._is_public_schema(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self._is_public_schema(request) and super().has_delete_permission(request, obj)


class PublicSchemaAdminMixin:
    """Only allow admin access on the public schema (Shop, Domain, User)."""

    def _ensure_public_schema(self):
        connection.set_schema_to_public()

    def _is_public_schema(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is not None:
            return tenant.schema_name == get_public_schema_name()

        # localhost with no matching domain leaves schema unset — still public admin
        if not connection.schema_name:
            return True
        return connection.schema_name == get_public_schema_name()

    def save_model(self, request, obj, form, change):
        self._ensure_public_schema()
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        self._ensure_public_schema()
        super().save_formset(request, form, formset, change)

    def delete_model(self, request, obj):
        self._ensure_public_schema()
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        self._ensure_public_schema()
        super().delete_queryset(request, queryset)

    def has_module_permission(self, request):
        return self._is_public_schema(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._is_public_schema(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self._is_public_schema(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self._is_public_schema(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._is_public_schema(request) and super().has_delete_permission(request, obj)
