
from django.urls import path
from apps.products.views import ProductVariantListView, ProductVariantDetailView

urlpatterns = [
    path("list/", ProductVariantListView.as_view({"get": "list"})),
    path("details/<int:pk>/", ProductVariantDetailView.as_view({"get": "retrieve"})),
]