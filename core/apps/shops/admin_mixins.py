from django.contrib import admin
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

    def _is_public_schema(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is not None:
            return tenant.schema_name == get_public_schema_name()
        from django.db import connection
        return connection.schema_name == get_public_schema_name()

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
