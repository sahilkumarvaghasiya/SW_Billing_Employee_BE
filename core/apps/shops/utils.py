from django.db import connection


def get_current_tenant_id():
    tenant = connection.tenant
    if tenant and getattr(tenant, "schema_name", None) != "public":
        return tenant.pk
    return None
