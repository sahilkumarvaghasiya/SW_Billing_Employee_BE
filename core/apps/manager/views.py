from datetime import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from apps.manager.pagination import ManagerBillsPagination, ManagerEmployeesPagination
from apps.manager.permissions import IsManager
from apps.manager.serializers import (
    ManagerBillListSerializer,
    ManagerEmployeeBlockSerializer,
    ManagerEmployeeCreateSerializer,
    ManagerEmployeeListSerializer,
)
from apps.accounts.models import User
from apps.sales.models import Bill, BillItem
from apps.sales.utils import format_indian_amount


class ManagerOverviewViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsManager]
    http_method_names = ["get"]
    queryset = Bill.objects.none()

    def list(self, request, *args, **kwargs):
        params = request.query_params

        start_date_param = (params.get("start_date") or "").strip()
        end_date_param = (params.get("end_date") or "").strip()

        today = timezone.localdate()

        if start_date_param:
            try:
                start_date = datetime.strptime(start_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError(
                    {"start_date": ["Invalid date format. Use DD-MM-YYYY."]}
                ) from exc
        else:
            start_date = today

        if end_date_param:
            try:
                end_date = datetime.strptime(end_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError(
                    {"end_date": ["Invalid date format. Use DD-MM-YYYY."]}
                ) from exc
        else:
            end_date = today

        if start_date > end_date:
            raise ValidationError(
                {"date_range": ["start_date cannot be greater than end_date."]}
            )

        bills = Bill.objects.filter(
            payment_status=Bill.PaymentStatus.PAID,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )

        bill_agg = bills.aggregate(
            revenue=Sum("total_amount"),
            bill_count=Count("id"),
        )
        revenue = bill_agg["revenue"] or Decimal("0.00")
        bill_count = bill_agg["bill_count"] or 0

        average_revenue = (revenue / bill_count) if bill_count else Decimal("0.00")

        total_products_sold = (
            BillItem.objects.filter(bill__in=bills).aggregate(total=Sum("quantity"))[
                "total"
            ]
            or 0
        )
        average_products_sold = (total_products_sold / bill_count) if bill_count else 0

        revenue_trend = self._build_revenue_trend(bills, start_date, end_date)

        return Response(
            {
                "start_date": start_date.strftime("%d-%m-%Y"),
                "end_date": end_date.strftime("%d-%m-%Y"),
                "revenue": format_indian_amount(revenue),
                "total_bills": bill_count,
                "average_revenue": format_indian_amount(average_revenue),
                "average_products_sold": round(float(average_products_sold), 2),
                "revenue_trend": revenue_trend,
            },
            status=status.HTTP_200_OK,
        )

    def _build_revenue_trend(self, bills, start_date, end_date):
        total_days = (end_date - start_date).days + 1

        if total_days <= 31:
            granularity = "daily"
            trunc = TruncDate("created_at")
            label_format = "%d-%m-%Y"
        elif total_days <= 730:
            granularity = "monthly"
            trunc = TruncMonth("created_at")
            label_format = "%m-%Y"
        else:
            granularity = "yearly"
            trunc = TruncYear("created_at")
            label_format = "%Y"

        rows = (
            bills.annotate(period=trunc)
            .values("period")
            .annotate(revenue=Sum("total_amount"))
            .order_by("period")
        )

        points = [
            {
                "label": row["period"].strftime(label_format),
                "revenue": format_indian_amount(row["revenue"] or Decimal("0.00")),
            }
            for row in rows
            if row["period"] is not None
        ]

        return {
            "granularity": granularity,
            "points": points,
        }


class ManagerBillsViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsManager]
    serializer_class = ManagerBillListSerializer
    pagination_class = ManagerBillsPagination
    http_method_names = ["get"]

    def get_queryset(self):
        params = self.request.query_params

        start_date_param = (params.get("start_date") or "").strip()
        end_date_param = (params.get("end_date") or "").strip()
        search = (params.get("search") or "").strip()

        queryset = Bill.objects.select_related("customer", "created_by").filter(
            is_active=True,
        )

        if start_date_param:
            try:
                start_date = datetime.strptime(start_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError(
                    {"start_date": ["Invalid date format. Use DD-MM-YYYY."]}
                ) from exc
            queryset = queryset.filter(created_at__date__gte=start_date)

        if end_date_param:
            try:
                end_date = datetime.strptime(end_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError(
                    {"end_date": ["Invalid date format. Use DD-MM-YYYY."]}
                ) from exc
            queryset = queryset.filter(created_at__date__lte=end_date)

        if search:
            queryset = queryset.filter(
                Q(bill_number__icontains=search)
                | Q(created_by__username__icontains=search)
            )

        return queryset.order_by("-created_at")


class ManagerEmployeeCreateViewSet(viewsets.ViewSet):
    permission_classes = [IsManager]
    http_method_names = ["post"]

    def create(self, request, *args, **kwargs):
        serializer = ManagerEmployeeCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "id": user.id,
                "name": user.username,
                "email": user.email,
                "phone_number": user.phone_number,
                "role": user.role,
                "password": serializer._generated_password,
            },
            status=status.HTTP_201_CREATED,
        )


class ManagerEmployeeLimitViewSet(viewsets.ViewSet):
    permission_classes = [IsManager]
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        shop = request.user.shop
        total_limit = shop.employee_limit
        used = shop.users.filter(role=User.Role.EMPLOYEE).count()
        remaining = max(total_limit - used, 0)

        return Response(
            {
                "employee_limit": total_limit,
                "used": used,
                "remaining": remaining,
            },
            status=status.HTTP_200_OK,
        )


class ManagerEmployeeListViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsManager]
    serializer_class = ManagerEmployeeListSerializer
    pagination_class = ManagerEmployeesPagination
    http_method_names = ["get"]

    def get_queryset(self):
        return self.request.user.shop.users.filter(role=User.Role.EMPLOYEE).order_by(
            "-date_joined"
        )


class ManagerEmployeeManageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsManager]
    serializer_class = ManagerEmployeeListSerializer
    http_method_names = ["patch", "delete"]

    def get_queryset(self):
        return self.request.user.shop.users.filter(role=User.Role.EMPLOYEE)

    def partial_update(self, request, *args, **kwargs):
        employee = self.get_object()

        serializer = ManagerEmployeeBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_blocked = serializer.validated_data["is_blocked"]

        employee.is_blocked = is_blocked
        employee.save()

        message = (
            "User blocked successfully."
            if is_blocked
            else "User unblocked successfully."
        )
        return Response({"message": message}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        employee = self.get_object()

        force = str(
            request.query_params.get("force") or request.data.get("force") or ""
        ).strip().lower() in ("1", "true", "yes")

        employee_bills = Bill.objects.filter(created_by_id=employee.pk)
        bills_count = employee_bills.count()

        if bills_count and not force:
            return Response(
                {
                    "requires_confirmation": True,
                    "bills_count": bills_count,
                    "detail": (
                        f"This employee has created {bills_count} bill(s). "
                        "Deleting will also permanently delete all of their bills. "
                        "Confirm to continue."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            if bills_count:
                employee_bills.delete()
            employee.delete()

        return Response(
            {"message": "User and their data deleted successfully."},
            status=status.HTTP_200_OK,
        )


class ManagerStaffPerformanceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsManager]
    http_method_names = ["get"]
    queryset = User.objects.none()

    def get_queryset(self):
        return self.request.user.shop.users.filter(role=User.Role.EMPLOYEE).order_by(
            "username"
        )

    def list(self, request, *args, **kwargs):
        params = request.query_params
        start_date_param = (params.get("start_date") or "").strip()
        end_date_param = (params.get("end_date") or "").strip()

        today = timezone.localdate()

        if start_date_param:
            try:
                start_date = datetime.strptime(start_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError(
                    {"start_date": ["Invalid date format. Use DD-MM-YYYY."]}
                ) from exc
        else:
            start_date = today

        if end_date_param:
            try:
                end_date = datetime.strptime(end_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError(
                    {"end_date": ["Invalid date format. Use DD-MM-YYYY."]}
                ) from exc
        else:
            end_date = today

        if start_date > end_date:
            raise ValidationError(
                {"date_range": ["start_date cannot be greater than end_date."]}
            )

        employees = self.get_queryset()

        results = []
        for employee in employees:
            agg = Bill.objects.filter(
                created_by=employee,
                payment_status=Bill.PaymentStatus.PAID,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            ).aggregate(
                bills_generated=Count("id"),
                revenue=Sum("total_amount"),
            )
            results.append(
                {
                    "id": employee.id,
                    "name": employee.username,
                    "bills_generated": agg["bills_generated"] or 0,
                    "revenue": format_indian_amount(agg["revenue"] or Decimal("0.00")),
                }
            )

        return Response(
            {
                "start_date": start_date.strftime("%d-%m-%Y"),
                "end_date": end_date.strftime("%d-%m-%Y"),
                "staff_performance": results,
            },
            status=status.HTTP_200_OK,
        )
