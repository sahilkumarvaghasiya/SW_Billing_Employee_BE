
from django.urls import path
from apps.vendors.views import (
    GenerateBarcodeViewSet,
    VendorListViewSet,
    VendorStockCreateViewSet,
    VendorExistingStockCreateViewSet,
    VendorStockHistoryListViewset,
    VendorStockHistoryDetailsViewset,
    VendorValidationViewSet,
)

urlpatterns = [
    path("list/", VendorListViewSet.as_view({"get": "list"})),
    path("validate/", VendorValidationViewSet.as_view({"post": "create"})),
    path("stock/generate-barcode/", GenerateBarcodeViewSet.as_view({"post": "create"})),
    path("stock/create/", VendorStockCreateViewSet.as_view({"post": "create"})),
    path("existing/<int:id>/stock/create/", VendorExistingStockCreateViewSet.as_view({"post": "create"})),
    path("stock/<int:id>/history/list/", VendorStockHistoryListViewset.as_view({"get": "list"})),
    path("stock/history/details/", VendorStockHistoryDetailsViewset.as_view({"get": "list"})),
]