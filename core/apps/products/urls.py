
from django.urls import path
from apps.products.views import (
    ColorDropdownListView,
    ItemTypeDropdownListView,
    ProductVariantDetailView,
    ProductVariantListView,
    SizeDropdownListView,
)

urlpatterns = [
    path("list/", ProductVariantListView.as_view({"get": "list"})),
    path("details/<int:pk>/", ProductVariantDetailView.as_view({"get": "retrieve"})),
    path("sizes/list/", SizeDropdownListView.as_view({"get": "list"})),
    path("item-types/list/", ItemTypeDropdownListView.as_view({"get": "list"})),
    path("colors/list/", ColorDropdownListView.as_view({"get": "list"})),
]