from django.urls import include, path
from rest_framework.routers import DefaultRouter
from apps.manager.views import (
    ManagerBillsViewSet,
    ManagerEmployeeCreateViewSet,
    ManagerEmployeeLimitViewSet,
    ManagerEmployeeListViewSet,
    ManagerEmployeeManageViewSet,
    ManagerOverviewViewSet,
    ManagerPaymentConfigViewSet,
    ManagerStaffPerformanceViewSet,
)


router = DefaultRouter()
router.register("payment-configs", ManagerPaymentConfigViewSet, basename="payment-config")


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
    path("", include(router.urls)),
]
