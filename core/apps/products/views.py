from rest_framework import viewsets
from apps.accounts.permissions import IsEmployee
from django_filters.rest_framework import DjangoFilterBackend
from apps.products.models import Color, ItemType, ProductVariant, Size
from apps.products.serializers import (
    ColorDropdownSerializer,
    ItemTypeDropdownSerializer,
    ProductVariantListSerializer,
    ProductVariantDetailSerializer,
    SizeDropdownSerializer,
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
        user = self.request.user

        return ProductVariant.objects.select_related(
            "product", "size"
        ).filter(
            product__shop=user.shop,  
            is_active=True
        ).order_by("-created_at")
    
class ProductVariantDetailView(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductVariantDetailSerializer
    permission_classes = [IsEmployee]

    def get_queryset(self):
        user = self.request.user

        return ProductVariant.objects.select_related(
            "product", "size"
        ).filter(
            product__shop=user.shop,
            is_active=True
        )


class SizeDropdownListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = SizeDropdownSerializer
    pagination_class = DropdownPagination
    permission_classes = [IsEmployee]
    http_method_names = ["get"]

    def get_queryset(self):
        user = self.request.user
        search = (self.request.query_params.get("search") or "").strip()

        queryset = Size.objects.filter(shop=user.shop)

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("-created_at")


class ItemTypeDropdownListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemTypeDropdownSerializer
    pagination_class = DropdownPagination
    permission_classes = [IsEmployee]
    http_method_names = ["get"]

    def get_queryset(self):
        user = self.request.user
        search = (self.request.query_params.get("search") or "").strip()

        queryset = ItemType.objects.filter(shop=user.shop)

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("-created_at")


class ColorDropdownListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = ColorDropdownSerializer
    pagination_class = DropdownPagination
    permission_classes = [IsEmployee]
    http_method_names = ["get"]

    def get_queryset(self):
        user = self.request.user
        search = (self.request.query_params.get("search") or "").strip()

        queryset = Color.objects.filter(shop=user.shop)

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("-created_at")