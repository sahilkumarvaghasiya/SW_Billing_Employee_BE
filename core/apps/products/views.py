from rest_framework import viewsets
from apps.accounts.permissions import IsEmployee
from django_filters.rest_framework import DjangoFilterBackend
from apps.products.models import ProductVariant
from apps.products.serializers import (
    ProductVariantListSerializer,
    ProductVariantDetailSerializer
)
from apps.products.filters import ProductVariantFilter
from apps.products.pagination import ProductPagination

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