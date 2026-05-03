import django_filters
from django.db.models import Q
from apps.products.models import ProductVariant
from datetime import datetime, time


class ProductVariantFilter(django_filters.FilterSet):

    search = django_filters.CharFilter(method="filter_search")
    size_id = django_filters.NumberFilter(field_name="size__id")
    color_id = django_filters.NumberFilter(field_name="color__id")
    gender = django_filters.CharFilter(method="filter_gender")
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    start_date = django_filters.CharFilter(method="filter_start_date")
    end_date = django_filters.CharFilter(method="filter_end_date")
    class Meta:
        model = ProductVariant
        fields = []

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset

        return queryset.filter(
            Q(product__item_type__name__icontains=value) |
            Q(product__name__icontains=value) |
            Q(product__company__name__icontains=value)
        )

    def filter_gender(self, queryset, name, value):
        if not value:
            return queryset

        genders = [gender.strip() for gender in value.split(",") if gender.strip()]
        if not genders:
            return queryset

        gender_query = Q()
        for gender in genders:
            gender_query |= Q(product__gender__iexact=gender)

        return queryset.filter(gender_query)


    def filter_start_date(self, queryset, name, value):
        if not value:
            return queryset

        try:
            date_obj = datetime.strptime(value, "%d-%m-%Y").date()
            start_datetime = datetime.combine(date_obj, time.min)  
            return queryset.filter(created_at__gte=start_datetime)
        except ValueError:
            return queryset

    def filter_end_date(self, queryset, name, value):
        if not value:
            return queryset
        try:
            date_obj = datetime.strptime(value, "%d-%m-%Y").date()
            end_datetime = datetime.combine(date_obj, time.max)
            return queryset.filter(created_at__lte=end_datetime)
        except ValueError:
            return queryset