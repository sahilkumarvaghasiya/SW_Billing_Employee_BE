from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.manager.permissions import IsManager
from apps.manager.serializers import (
    CreateDashboardUserSerializer,
    DashboardUserSerializer,
    PaymentConfigSerializer,
    PaymentConfigWriteSerializer,
    StockItemSerializer,
    StockUpdateSerializer,
    UserStatusSerializer,
    timezone_format,
)
from apps.manager.utils import format_inr, parse_date_range
from apps.products.models import ProductVariant
from apps.sales.models import Bill, BillItem, Notification, PaymentConfig


class ManagerUsersListCreateView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        shop = request.user.shop
        users = shop.users.exclude(id=request.user.id).order_by("-date_joined")
        data = DashboardUserSerializer(users, many=True).data
        return Response(data)

    def post(self, request):
        serializer = CreateDashboardUserSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            DashboardUserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class ManagerUserStatusView(APIView):
    permission_classes = [IsManager]

    def patch(self, request, user_id):
        shop = request.user.shop
        try:
            user = shop.users.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=404)

        if user.role == User.Role.MANAGER and user.id != request.user.id:
            return Response(
                {"detail": "Cannot change status of another manager."},
                status=400,
            )

        serializer = UserStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_active = serializer.validated_data["status"] == "active"
        user.is_blocked = not is_active
        user.is_active = is_active
        user.save(update_fields=["is_blocked", "is_active"])
        return Response(DashboardUserSerializer(user).data)


class ManagerStaffPerformanceView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        range_type = request.query_params.get("range", "day")
        date_str = request.query_params.get("date", "")
        start, end = parse_date_range(range_type, date_str)
        shop = request.user.shop

        staff = shop.users.filter(role=User.Role.EMPLOYEE)
        results = []

        for employee in staff:
            bills = Bill.objects.filter(
                created_by=employee,
                payment_status=Bill.PaymentStatus.PAID,
                created_at__date__gte=start,
                created_at__date__lte=end,
            )
            agg = bills.aggregate(
                total=Sum("total_amount"),
                count=Count("id"),
            )
            results.append(
                {
                    "userId": str(employee.id),
                    "staffName": employee.username,
                    "billsCount": agg["count"] or 0,
                    "revenue": format_inr(agg["total"] or 0),
                }
            )

        return Response(results)


class ManagerOverviewView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        range_type = request.query_params.get("range", "day")
        date_str = request.query_params.get("date", "")
        start, end = parse_date_range(range_type, date_str)

        paid_bills = Bill.objects.filter(
            payment_status=Bill.PaymentStatus.PAID,
            created_at__date__gte=start,
            created_at__date__lte=end,
        )

        agg = paid_bills.aggregate(
            revenue=Sum("total_amount"),
            tx_count=Count("id"),
        )
        revenue = agg["revenue"] or Decimal("0.00")
        tx_count = agg["tx_count"] or 0
        avg = revenue / tx_count if tx_count else Decimal("0.00")

        critical = Notification.objects.filter(
            priority=Notification.Priority.HIGH,
            created_at__date__gte=start,
            created_at__date__lte=end,
        ).count()

        trend = self._revenue_trend(start, end, range_type)
        payment_split = self._payment_split(paid_bills)

        return Response(
            {
                "revenue": format_inr(revenue),
                "txCount": tx_count,
                "avgOrderValue": format_inr(avg),
                "criticalAlerts": critical,
                "revenueTrend": trend,
                "paymentSplit": payment_split,
            }
        )

    def _revenue_trend(self, start, end, range_type):
        paid = Bill.objects.filter(
            payment_status=Bill.PaymentStatus.PAID,
            created_at__date__gte=start,
            created_at__date__lte=end,
        )

        if range_type == "day":
            hourly = {}
            for bill in paid:
                hour = timezone.localtime(bill.created_at).hour
                label = f"{hour:02d}:00"
                hourly[label] = hourly.get(label, 0) + float(bill.total_amount)
            return [{"label": k, "revenue": v} for k, v in sorted(hourly.items())]

        daily = (
            paid.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(revenue=Sum("total_amount"))
            .order_by("day")
        )
        return [
            {
                "label": row["day"].strftime("%d %b"),
                "revenue": float(row["revenue"] or 0),
            }
            for row in daily
        ]

    def _payment_split(self, queryset):
        totals = queryset.values("payment_method").annotate(
            total=Sum("total_amount")
        )
        label_map = {
            Bill.PaymentMethod.CASH: "Cash",
            Bill.PaymentMethod.CARD: "Card",
            Bill.PaymentMethod.QR: "UPI / QR",
        }
        return [
            {
                "method": label_map.get(row["payment_method"], row["payment_method"]),
                "value": float(row["total"] or 0),
            }
            for row in totals
        ]


class ManagerOverviewSalesView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        range_type = request.query_params.get("range", "day")
        date_str = request.query_params.get("date", "")
        brand = (request.query_params.get("brand") or "").strip().lower()
        category = (request.query_params.get("category") or "").strip().lower()
        start, end = parse_date_range(range_type, date_str)

        items = (
            BillItem.objects.filter(
                bill__payment_status=Bill.PaymentStatus.PAID,
                bill__created_at__date__gte=start,
                bill__created_at__date__lte=end,
            )
            .select_related(
                "product_variant__product__company",
                "product_variant__product__item_type",
            )
            .values(
                "product_variant_id",
                "product_variant__barcode_number",
                "product_variant__product__item_type__name",
                "product_variant__product__company__name",
                "product_variant__product__gender",
            )
            .annotate(sales=Sum("quantity"))
            .order_by("-sales")[:50]
        )

        results = []
        for row in items:
            item_brand = (row["product_variant__product__company__name"] or "").lower()
            item_category = (row["product_variant__product__gender"] or "general").lower()
            if brand and brand not in item_brand:
                continue
            if category and category not in item_category:
                continue
            results.append(
                {
                    "id": str(row["product_variant_id"]),
                    "sku": row["product_variant__barcode_number"] or "—",
                    "name": (
                        row["product_variant__product__item_type__name"] or "Product"
                    ).title(),
                    "brand": (
                        row["product_variant__product__company__name"] or "—"
                    ).title(),
                    "category": item_category.title(),
                    "sales": int(row["sales"] or 0),
                }
            )

        return Response(results)


class ManagerBillsView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        range_type = request.query_params.get("range", "day")
        date_str = request.query_params.get("date", "")
        start, end = parse_date_range(range_type, date_str)

        bills = (
            Bill.objects.filter(
                created_at__date__gte=start,
                created_at__date__lte=end,
            )
            .select_related("created_by")
            .order_by("-created_at")[:200]
        )

        data = []
        for bill in bills:
            item_count = bill.bill_items.aggregate(total=Sum("quantity"))["total"] or 0
            status_label = (
                "completed"
                if bill.payment_status == Bill.PaymentStatus.PAID
                else "pending"
            )
            data.append(
                {
                    "id": str(bill.id),
                    "billNumber": bill.bill_number,
                    "staffName": bill.created_by.username,
                    "amount": float(bill.total_amount),
                    "itemCount": int(item_count),
                    "timestamp": timezone_format(bill.created_at),
                    "status": status_label,
                }
            )

        return Response(data)


class ManagerActivityView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        bills = (
            Bill.objects.select_related("created_by")
            .order_by("-created_at")[:100]
        )
        logs = []
        for bill in bills:
            logs.append(
                {
                    "id": f"bill-{bill.id}",
                    "timestamp": timezone_format(bill.created_at),
                    "actor": bill.created_by.username,
                    "action": f"Created bill {bill.bill_number}",
                    "meta": f"{bill.get_payment_method_display()} · {format_inr(bill.total_amount)}",
                }
            )

        configs = PaymentConfig.objects.order_by("-updated_at")[:20]
        for cfg in configs:
            logs.append(
                {
                    "id": f"cfg-{cfg.id}",
                    "timestamp": timezone_format(cfg.updated_at),
                    "actor": "Manager",
                    "action": f"Payment QR: {cfg.name}",
                    "meta": "Active" if cfg.is_active else "Inactive",
                }
            )

        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        return Response(logs[:80])


class ManagerStockListView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        variants = (
            ProductVariant.objects.filter(is_active=True)
            .select_related("product__company", "product__item_type", "size", "color")
            .order_by("-updated_at")[:500]
        )
        return Response(
            StockItemSerializer(variants, many=True).data
        )


class ManagerStockDetailView(APIView):
    permission_classes = [IsManager]

    def patch(self, request, item_id):
        try:
            variant = ProductVariant.objects.select_related("product").get(pk=item_id)
        except ProductVariant.DoesNotExist:
            return Response({"detail": "Item not found."}, status=404)

        serializer = StockUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "price" in data:
            variant.price = data["price"]
        if "qty" in data:
            variant.quantity = data["qty"]
        variant.save()

        return Response(StockItemSerializer(variant).data)


class ManagerReportsView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        today = timezone.localdate()
        month_start = today.replace(day=1)

        month_bills = Bill.objects.filter(
            payment_status=Bill.PaymentStatus.PAID,
            created_at__date__gte=month_start,
        )
        month_revenue = month_bills.aggregate(total=Sum("total_amount"))["total"] or 0
        month_count = month_bills.count()

        active_staff = request.user.shop.users.filter(
            role=User.Role.EMPLOYEE,
            is_blocked=False,
            is_active=True,
        ).count()

        low_stock = ProductVariant.objects.filter(
            is_active=True,
            quantity__lte=5,
            quantity__gt=0,
        ).count()

        qr_configs = PaymentConfig.objects.filter(is_active=True).count()

        return Response(
            [
                {
                    "id": "month-revenue",
                    "title": "Monthly Revenue",
                    "description": "Paid bills this month",
                    "value": format_inr(month_revenue),
                },
                {
                    "id": "month-bills",
                    "title": "Bills This Month",
                    "description": "Total completed transactions",
                    "value": str(month_count),
                },
                {
                    "id": "active-staff",
                    "title": "Active Staff",
                    "description": "Employees not blocked",
                    "value": str(active_staff),
                },
                {
                    "id": "low-stock",
                    "title": "Low Stock Items",
                    "description": "Variants at or below threshold",
                    "value": str(low_stock),
                },
                {
                    "id": "payment-qr",
                    "title": "Payment QR Codes",
                    "description": "Active configs for billing app",
                    "value": str(qr_configs),
                },
            ]
        )


class ManagerAlertsView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        notifications = Notification.objects.order_by("-created_at")[:50]
        severity_map = {
            Notification.Priority.HIGH: "critical",
            Notification.Priority.MEDIUM: "warning",
            Notification.Priority.LOW: "info",
        }
        data = []
        for n in notifications:
            data.append(
                {
                    "id": str(n.id),
                    "severity": severity_map.get(n.priority, "info"),
                    "title": n.title,
                    "message": n.message,
                    "timestamp": timezone_format(n.created_at),
                    "seen": False,
                }
            )
        return Response(data)


class ManagerPaymentConfigListCreateView(APIView):
    permission_classes = [IsManager]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        configs = PaymentConfig.objects.order_by("-created_at")
        return Response(
            PaymentConfigSerializer(configs, many=True, context={"request": request}).data
        )

    def post(self, request):
        serializer = PaymentConfigWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = serializer.save()
        return Response(
            PaymentConfigSerializer(config, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ManagerPaymentConfigDetailView(APIView):
    permission_classes = [IsManager]
    parser_classes = [MultiPartParser, FormParser]

    def patch(self, request, config_id):
        try:
            config = PaymentConfig.objects.get(pk=config_id)
        except PaymentConfig.DoesNotExist:
            return Response({"detail": "Payment config not found."}, status=404)

        serializer = PaymentConfigWriteSerializer(
            config,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        config = serializer.save()
        return Response(
            PaymentConfigSerializer(config, context={"request": request}).data
        )

    def delete(self, request, config_id):
        try:
            config = PaymentConfig.objects.get(pk=config_id)
        except PaymentConfig.DoesNotExist:
            return Response({"detail": "Payment config not found."}, status=404)

        config.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
