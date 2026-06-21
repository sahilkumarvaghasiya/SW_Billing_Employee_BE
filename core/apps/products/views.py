from rest_framework import viewsets
from apps.accounts.permissions import IsEmployee
from apps.manager.permissions import IsManager
from django_filters.rest_framework import DjangoFilterBackend
from apps.products.models import Color, ItemType, ProductVariant, Size, Company
from apps.products.serializers import (
    ColorDropdownSerializer,
    ItemTypeDropdownSerializer,
    ProductVariantListSerializer,
    ProductVariantDetailSerializer,
    SizeDropdownSerializer,
    BrandDropdownSerializer,
)
from apps.products.filters import ProductVariantFilter
from apps.products.pagination import ProductPagination, DropdownPagination

class ProductVariantListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductVariantListSerializer
    pagination_class = ProductPagination
    filter_backends = [DjangoFilterBackend]
    permission_classes = [IsEmployee]
    filterset_class = ProductVariantFilter

    def get_queryset(self):
        return ProductVariant.objects.select_related(
            "product", "size", "color", "product__item_type", "product__company"
        ).filter(
            is_active=True
        ).order_by("-created_at")
    
class ProductVariantDetailView(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductVariantDetailSerializer
    permission_classes = [IsEmployee]

    def get_queryset(self):
        return ProductVariant.objects.select_related(
            "product", "size"
        ).filter(
            is_active=True
        )


class SizeDropdownListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = SizeDropdownSerializer
    pagination_class = DropdownPagination
    permission_classes = [IsEmployee | IsManager]
    http_method_names = ["get"]

    def get_queryset(self):
        search = (self.request.query_params.get("search") or "").strip()

        queryset = Size.objects.all()

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("-created_at")


class ItemTypeDropdownListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemTypeDropdownSerializer
    pagination_class = DropdownPagination
    permission_classes = [IsEmployee | IsManager]
    http_method_names = ["get"]

    def get_queryset(self):
        search = (self.request.query_params.get("search") or "").strip()

        queryset = ItemType.objects.all()

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("-created_at")


class ColorDropdownListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = ColorDropdownSerializer
    pagination_class = DropdownPagination
    permission_classes = [IsEmployee | IsManager]
    http_method_names = ["get"]

    def get_queryset(self):
        search = (self.request.query_params.get("search") or "").strip()

        queryset = Color.objects.all()

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("-created_at")
    

class BrandDropdownListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = BrandDropdownSerializer
    pagination_class = DropdownPagination
    permission_classes = [IsEmployee | IsManager]
    http_method_names = ["get"]

    def get_queryset(self):
        search = (self.request.query_params.get("search") or "").strip()

        queryset = Company.objects.all()

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("-created_at")
