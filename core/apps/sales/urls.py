from django.urls import path
from apps.sales.views import (
    BarcodeProductLookupListView,
    BillCreateViewSet,
    CustomerLookupByPhoneViewSet,
    NotificationMarkSeenViewSet,
    NotificationUnreadListViewSet,
    PaymentConfigQRListViewSet,
    SalesHistoryDetailViewSet,
    SalesHistoryListViewSet,
    SendWhatsAppInvoiceView,
    TodaySummaryViewSet,
)


urlpatterns = [
    path("barcode-lookup/<str:barcode_number>/", BarcodeProductLookupListView.as_view({"get": "list"})),
    path("customer-lookup/<str:phone>/", CustomerLookupByPhoneViewSet.as_view({"get": "list"})),
    path("payment-configs/qr/", PaymentConfigQRListViewSet.as_view({"get": "list"})),
    path("bills/create/", BillCreateViewSet.as_view({"post": "create"})),
    path("bills/send-whatsapp-invoice/", SendWhatsAppInvoiceView.as_view()),
    path("today-summary/", TodaySummaryViewSet.as_view({"get": "list"})),
    path("historylist/", SalesHistoryListViewSet.as_view({"get": "list"})),
    path("saleshistory/details/<uuid:pk>/", SalesHistoryDetailViewSet.as_view({"get": "retrieve"})),
    path("notifications/", NotificationUnreadListViewSet.as_view({"get": "list"})),
    path("notifications/mark-seen/", NotificationMarkSeenViewSet.as_view({"post": "create"})),
]
