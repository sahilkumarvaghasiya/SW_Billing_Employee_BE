from django.contrib import admin
from django.utils.text import capfirst

from apps.accounts.models import User
from apps.shops.admin_mixins import PublicSchemaAdminMixin
from apps.shops.models import Domain, Shop
from apps.shops.shop_delete import delete_shop


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 1


@admin.register(Shop)
class ShopAdmin(PublicSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "schema_name", "employee_limit")
    search_fields = ("name", "schema_name")
    list_filter = ("employee_limit",)
    inlines = [DomainInline]

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        self._ensure_public_schema()
        return super().changeform_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        self._ensure_public_schema()
        return super().add_view(request, form_url, extra_context)

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
        self._ensure_public_schema()
        self._delete_shop(obj)

    def delete_queryset(self, request, queryset):
        self._ensure_public_schema()
        for obj in queryset:
            self._delete_shop(obj)

    def _delete_shop(self, shop):
        delete_shop(shop)


@admin.register(Domain)
class DomainAdmin(PublicSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    search_fields = ("domain", "tenant__name")
