
from django.urls import path
from apps.vendors.views import (
    GenerateBarcodeViewSet,
    ScanExistingProductViewSet,
    VendorListViewSet,
    VendorPayableBillDetailViewSet,
    VendorPayableInfoViewSet,
    VendorPayablePayViewSet,
    VendorPayablePaymentDetailViewSet,
    VendorPayablePendingBillsViewSet,
    VendorPayableReportPdfViewSet,
    VendorPayableReportPreviewViewSet,
    VendorPayableStatementViewSet,
    VendorPayableSummaryViewSet,
    VendorPayableVendorsViewSet,
    VendorStockCreateViewSet,
    VendorExistingProductsViewSet,
    VendorExistingStockCreateViewSet,
    VendorStockHistoryListViewset,
    VendorStockHistoryDetailsViewset,
    VendorValidationViewSet,
)

urlpatterns = [
    path("list/", VendorListViewSet.as_view({"get": "list"})),
    path("validate/", VendorValidationViewSet.as_view({"post": "create"})),
    path("payable/summary/", VendorPayableSummaryViewSet.as_view({"get": "list"})),
    path(
        "payable/reports/preview/",
        VendorPayableReportPreviewViewSet.as_view({"get": "list"}),
    ),
    path(
        "payable/reports/pdf/",
        VendorPayableReportPdfViewSet.as_view({"get": "list"}),
    ),
    path("payable/vendors/", VendorPayableVendorsViewSet.as_view({"get": "list"})),
    path(
        "payable/vendors/<int:id>/info/",
        VendorPayableInfoViewSet.as_view({"get": "retrieve"}),
    ),
    path(
        "payable/vendors/<int:id>/pending/",
        VendorPayablePendingBillsViewSet.as_view({"get": "list"}),
    ),
    path(
        "payable/vendors/<int:id>/pay/",
        VendorPayablePayViewSet.as_view({"post": "create"}),
    ),
    path(
        "payable/vendors/<int:id>/statement/",
        VendorPayableStatementViewSet.as_view({"get": "list"}),
    ),
    path(
        "payable/payments/<int:id>/",
        VendorPayablePaymentDetailViewSet.as_view({"get": "retrieve"}),
    ),
    path(
        "payable/bills/<int:id>/",
        VendorPayableBillDetailViewSet.as_view({"get": "retrieve"}),
    ),
    path("stock/generate-barcode/", GenerateBarcodeViewSet.as_view({"post": "create"})),
    path("stock/scan/<str:barcode_number>/", ScanExistingProductViewSet.as_view({"get": "retrieve"})),
    path("stock/create/", VendorStockCreateViewSet.as_view({"post": "create"})),
    path(
        "existing/<int:id>/products/",
        VendorExistingProductsViewSet.as_view({"get": "list"}),
    ),
    path("existing/<int:id>/stock/create/", VendorExistingStockCreateViewSet.as_view({"post": "create"})),
    path("stock/<int:id>/history/list/", VendorStockHistoryListViewset.as_view({"get": "list"})),
    path("stock/history/details/", VendorStockHistoryDetailsViewset.as_view({"get": "list"})),
]