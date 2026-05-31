from django.contrib import admin
from django.utils.text import capfirst
from django_tenants.admin import TenantAdminMixin

from apps.accounts.models import User
from apps.shops.admin_mixins import PublicSchemaAdminMixin
from apps.shops.models import Domain, Shop


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 1


@admin.register(Shop)
class ShopAdmin(PublicSchemaAdminMixin, TenantAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "schema_name", "employee_limit")
    search_fields = ("name", "schema_name")
    list_filter = ("employee_limit",)
    inlines = [DomainInline]

    def get_deleted_objects(self, objs, request):
        """Only list public-schema objects; skip tenant tables like billing_bills."""
        to_delete = []
        model_count = {}

        for obj in objs:
            to_delete.append([f"{capfirst(Shop._meta.verbose_name)}: {obj}"])

            domains = obj.domains.all()
            for domain in domains:
                to_delete.append([f"  Domain: {domain.domain}"])

            users = User.objects.filter(shop=obj)
            user_count = users.count()
            if user_count:
                to_delete.append([f"  Users: {user_count} user(s)"])

            to_delete.append([
                f"  Tenant schema '{obj.schema_name}' "
                f"(all products, bills, vendors, etc.)"
            ])

            model_count[Shop._meta.verbose_name_plural] = (
                model_count.get(Shop._meta.verbose_name_plural, 0) + 1
            )
            model_count["domains"] = model_count.get("domains", 0) + domains.count()
            if user_count:
                model_count[User._meta.verbose_name_plural] = (
                    model_count.get(User._meta.verbose_name_plural, 0) + user_count
                )

        return to_delete, model_count, set(), []

    def delete_model(self, request, obj):
        self._delete_shop(obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self._delete_shop(obj)

    def _delete_shop(self, shop):
        shop_pk = shop.pk

        try:
            shop._drop_schema(force_drop=True)
        except Exception:
            pass

        user_qs = User.objects.filter(shop_id=shop_pk)
        user_qs._raw_delete(user_qs.db)

        domain_qs = Domain.objects.filter(tenant_id=shop_pk)
        domain_qs._raw_delete(domain_qs.db)

        shop_qs = Shop.objects.filter(pk=shop_pk)
        shop_qs._raw_delete(shop_qs.db)


@admin.register(Domain)
class DomainAdmin(PublicSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    search_fields = ("domain", "tenant__name")
