from django.urls import path

from apps.manager import views

urlpatterns = [
    path("users", views.ManagerUsersListCreateView.as_view()),
    path("users/<int:user_id>/status", views.ManagerUserStatusView.as_view()),
    path("users/performance", views.ManagerStaffPerformanceView.as_view()),
    path("overview", views.ManagerOverviewView.as_view()),
    path("overview/sales", views.ManagerOverviewSalesView.as_view()),
    path("bills", views.ManagerBillsView.as_view()),
    path("activity", views.ManagerActivityView.as_view()),
    path("stock/items", views.ManagerStockListView.as_view()),
    path("stock/items/<int:item_id>", views.ManagerStockDetailView.as_view()),
    path("reports", views.ManagerReportsView.as_view()),
    path("alerts", views.ManagerAlertsView.as_view()),
    path("payment-configs", views.ManagerPaymentConfigListCreateView.as_view()),
    path(
        "payment-configs/<uuid:config_id>",
        views.ManagerPaymentConfigDetailView.as_view(),
    ),
]
