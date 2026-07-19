from django.urls import include, path
from rest_framework.routers import DefaultRouter
from apps.manager.views import (
    ManagerBillsViewSet,
    ManagerEmployeeCreateViewSet,
    ManagerEmployeeLimitViewSet,
    ManagerEmployeeListViewSet,
    ManagerEmployeeManageViewSet,
    ManagerLowStockBrandViewSet,
    ManagerLowStockItemTypeViewSet,
    ManagerLowStockItemsViewSet,
    ManagerOverviewViewSet,
    ManagerPaymentConfigViewSet,
    ManagerProductSalesTrendViewSet,
    ManagerStaffPerformanceViewSet,
    ManagerStockItemsDetailsViewSet,
    ManagerStockSummaryViewSet,
    ManagerStockThresholdViewSet,
    ManagerVendorBillsBulkPayViewSet,
    ManagerVendorBillsViewSet,
    ManagerVendorReportPdfViewSet,
    ManagerVendorReportViewSet,
    ManagerVendorSummaryViewSet,
)


router = DefaultRouter()
router.register(
    "payment-configs", ManagerPaymentConfigViewSet, basename="payment-config"
)
router.register(
    "stock/items-details",
    ManagerStockItemsDetailsViewSet,
    basename="stock-items-details",
)
router.register(
    "vendors/bills",
    ManagerVendorBillsViewSet,
    basename="vendor-bills",
)


urlpatterns = [
    path("overview/", ManagerOverviewViewSet.as_view({"get": "list"})),
    path("overview/bills/", ManagerBillsViewSet.as_view({"get": "list"})),
    path("employees/", ManagerEmployeeCreateViewSet.as_view({"post": "create"})),
    path("employees/list/", ManagerEmployeeListViewSet.as_view({"get": "list"})),
    path(
        "staff-performance/",
        ManagerStaffPerformanceViewSet.as_view({"get": "list"}),
    ),
    path("employees/limit/", ManagerEmployeeLimitViewSet.as_view({"get": "list"})),
    path(
        "employees/<int:pk>/block/",
        ManagerEmployeeManageViewSet.as_view({"patch": "partial_update"}),
    ),
    path(
        "employees/<int:pk>/delete/",
        ManagerEmployeeManageViewSet.as_view({"delete": "destroy"}),
    ),
    path("stock-summary/", ManagerStockSummaryViewSet.as_view({"get": "list"})),
    path(
        "stock/low-stock/brands/",
        ManagerLowStockBrandViewSet.as_view({"get": "list"}),
    ),
    path(
        "stock/low-stock/item-types/",
        ManagerLowStockItemTypeViewSet.as_view({"get": "list"}),
    ),
    path(
        "stock/low-stock/items-attention/",
        ManagerLowStockItemsViewSet.as_view({"get": "list"}),
    ),
    path(
        "stock/sales-trend/",
        ManagerProductSalesTrendViewSet.as_view({"get": "list"}),
    ),
    path(
        "settings/stock-threshold/",
        ManagerStockThresholdViewSet.as_view(
            {"get": "list", "patch": "partial_update"}
        ),
    ),
    path(
        "vendors/summary/",
        ManagerVendorSummaryViewSet.as_view({"get": "list"}),
    ),
    path(
        "vendors/reports/preview/",
        ManagerVendorReportViewSet.as_view({"get": "list"}),
    ),
    path(
        "vendors/reports/pdf/",
        ManagerVendorReportPdfViewSet.as_view({"get": "list"}),
    ),
    path(
        "vendors/bills/bulk-pay/",
        ManagerVendorBillsBulkPayViewSet.as_view({"post": "create"}),
    ),
    path("", include(router.urls)),
]
