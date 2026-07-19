from datetime import datetime, timedelta
from decimal import Decimal
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Count, DecimalField, F, Prefetch, Q, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth, TruncYear
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from apps.manager.pagination import (
    ManagerBillsPagination,
    ManagerEmployeesPagination,
    ManagerLowStockItemsPagination,
    ManagerProductSalesTrendPagination,
    ManagerStockItemsDetailsPagination,
    ManagerVendorBillsPagination,
)
from apps.manager.permissions import IsManager, IsManagerOrEmployee
from apps.manager.serializers import (
    ManagerBillListSerializer,
    ManagerBrandSerializer,
    ManagerEmployeeBlockSerializer,
    ManagerEmployeeCreateSerializer,
    ManagerEmployeeListSerializer,
    ManagerItemTypeSerializer,
    ManagerLowStockItemSerializer,
    ManagerPaymentConfigSerializer,
    ManagerProductSalesTrendItemSerializer,
    ManagerProductSalesTrendQuerySerializer,
    ManagerStockItemDetailsSerializer,
    ManagerStockItemUpdateSerializer,
    ManagerStockThresholdSerializer,
    ManagerVendorBillPaymentSerializer,
    ManagerVendorBillSerializer,
    ManagerVendorBillsBulkPaySerializer,
)
from apps.manager.services.vendor_report_pdf import generate_vendor_report_pdf
from apps.manager.utils import (
    parse_id_list,
    parse_timestamp_ordering,
    under_threshold_variants,
)
from apps.manager.vendor_report import (
    vendor_report_bill_rows,
    vendor_report_entries,
    vendor_report_payable_groups,
    vendor_report_summary,
)
from apps.accounts.models import User
from apps.products.models import Company, ItemType, Product, ProductVariant
from apps.sales.models import Bill, BillItem, PaymentConfig
from apps.sales.utils import format_indian_amount
from apps.vendors.models import StockEntry, StockEntryTopUp


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
        sort = (params.get("sort") or "").strip().lower()

        queryset = Bill.objects.select_related("customer", "created_by").filter(
            is_active=True,
        )

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

        queryset = queryset.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )

        if search:
            queryset = queryset.filter(
                Q(bill_number__icontains=search)
                | Q(created_by__username__icontains=search)
            )

        ordering = "created_at" if sort == "oldest" else "-created_at"
        return queryset.order_by(ordering)


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
        sort = (self.request.query_params.get("sort") or "").strip().lower()
        ordering = "date_joined" if sort == "oldest" else "-date_joined"

        return self.request.user.shop.users.filter(role=User.Role.EMPLOYEE).order_by(
            ordering
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


class ManagerPaymentConfigViewSet(viewsets.ModelViewSet):
    permission_classes = [IsManager]
    serializer_class = ManagerPaymentConfigSerializer
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        return PaymentConfig.objects.all().order_by("-created_at")


class ManagerStockSummaryViewSet(viewsets.ViewSet):
    permission_classes = [IsManager]
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        variants = ProductVariant.objects.filter(is_active=True)

        summary = variants.aggregate(
            total_stock=Count("id"),
            out_of_stock=Count("id", filter=Q(quantity=0)),
            low_stock=Count(
                "id",
                filter=Q(quantity__gt=0) & Q(quantity__lte=F("low_stock_threshold")),
            ),
        )

        return Response(
            {
                "total_stock": summary["total_stock"] or 0,
                "out_of_stock": summary["out_of_stock"] or 0,
                "low_stock": summary["low_stock"] or 0,
            },
            status=status.HTTP_200_OK,
        )


class ManagerLowStockBrandViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsManager]
    serializer_class = ManagerBrandSerializer
    http_method_names = ["get"]
    pagination_class = None

    def get_queryset(self):
        brand_ids = (
            under_threshold_variants()
            .exclude(product__company__isnull=True)
            .values_list("product__company", flat=True)
            .distinct()
        )
        queryset = Company.objects.filter(id__in=brand_ids)

        search = (self.request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("name")


class ManagerLowStockItemTypeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsManager]
    serializer_class = ManagerItemTypeSerializer
    http_method_names = ["get"]
    pagination_class = None

    def get_queryset(self):
        item_type_ids = (
            under_threshold_variants()
            .exclude(product__item_type__isnull=True)
            .values_list("product__item_type", flat=True)
            .distinct()
        )
        queryset = ItemType.objects.filter(id__in=item_type_ids)

        search = (self.request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("name")


class ManagerLowStockItemsViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsManager]
    serializer_class = ManagerLowStockItemSerializer
    pagination_class = ManagerLowStockItemsPagination
    http_method_names = ["get"]

    def get_queryset(self):
        params = self.request.query_params
        brand_ids = parse_id_list(params, "brand")
        item_type_ids = parse_id_list(params, "item_type")

        queryset = under_threshold_variants().select_related(
            "product", "product__company", "product__item_type"
        )
        if brand_ids:
            queryset = queryset.filter(product__company_id__in=brand_ids)
        if item_type_ids:
            queryset = queryset.filter(product__item_type_id__in=item_type_ids)

        return queryset.order_by("quantity")


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


class ManagerProductSalesTrendViewSet(viewsets.ViewSet):
    permission_classes = [IsManager]
    http_method_names = ["get"]

    @staticmethod
    def _build_query_data(params):
        """Flatten repeated/comma-separated list params for the serializer."""
        data = {
            "start_date": params.get("start_date"),
            "end_date": params.get("end_date"),
            "sort": params.get("sort"),
        }
        for key in ("gender", "item_type"):
            values = []
            for raw in params.getlist(key):
                values.extend(
                    part.strip() for part in str(raw).split(",") if part.strip()
                )
            data[key] = values
        return {k: v for k, v in data.items() if v not in (None, "")}

    def list(self, request, *args, **kwargs):
        query = ManagerProductSalesTrendQuerySerializer(
            data=self._build_query_data(request.query_params)
        )
        query.is_valid(raise_exception=True)
        data = query.validated_data

        start_date = data["start_date"]
        end_date = data["end_date"]
        genders = data["gender"]
        item_type_ids = data["item_type"]
        sort = data["sort"]

        queryset = BillItem.objects.filter(
            bill__payment_status=Bill.PaymentStatus.PAID,
            bill__created_at__date__gte=start_date,
            bill__created_at__date__lte=end_date,
        )

        if genders:
            queryset = queryset.filter(product_variant__product__gender__in=genders)
        if item_type_ids:
            queryset = queryset.filter(
                product_variant__product__item_type_id__in=item_type_ids
            )

        ordering = "total_sold" if sort == "least_sold" else "-total_sold"

        rows = (
            queryset.values(
                product_id=F("product_variant__product__id"),
                gender=F("product_variant__product__gender"),
                item_type_name=F("product_variant__product__item_type__name"),
                brand_name=F("product_variant__product__company__name"),
            )
            .annotate(total_sold=Sum("quantity"))
            .order_by(ordering, "product_id")
        )

        paginator = ManagerProductSalesTrendPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        results = ManagerProductSalesTrendItemSerializer(page, many=True).data

        return paginator.get_paginated_response(
            {
                "start_date": start_date.strftime("%d-%m-%Y"),
                "end_date": end_date.strftime("%d-%m-%Y"),
                "sort": sort,
                "results": results,
            }
        )


class ManagerStockItemsDetailsViewSet(viewsets.ModelViewSet):
    permission_classes = [IsManager]
    serializer_class = ManagerStockItemDetailsSerializer
    pagination_class = ManagerStockItemsDetailsPagination
    http_method_names = ["get", "patch", "delete"]

    def get_queryset(self):
        params = self.request.query_params

        brand_ids = parse_id_list(params, "brand")
        item_type_ids = parse_id_list(params, "item_type")
        color_ids = parse_id_list(params, "color")
        size_ids = parse_id_list(params, "size")

        genders = []
        valid_genders = {choice.value for choice in Product.GenderChoices}
        for raw in params.getlist("gender"):
            for part in str(raw).split(","):
                part = part.strip().lower()
                if part:
                    genders.append(part)
        invalid_genders = [g for g in genders if g not in valid_genders]
        if invalid_genders:
            raise ValidationError(
                {
                    "gender": [
                        f"Invalid gender(s) {invalid_genders}. "
                        f"Choose from {sorted(valid_genders)}."
                    ]
                }
            )

        queryset = ProductVariant.objects.filter(is_active=True).select_related(
            "product",
            "product__company",
            "product__item_type",
            "size",
            "color",
        )

        if brand_ids:
            queryset = queryset.filter(product__company_id__in=brand_ids)
        if item_type_ids:
            queryset = queryset.filter(product__item_type_id__in=item_type_ids)
        if color_ids:
            queryset = queryset.filter(color_id__in=color_ids)
        if size_ids:
            queryset = queryset.filter(size_id__in=size_ids)
        if genders:
            queryset = queryset.filter(product__gender__in=genders)

        return queryset.order_by(*parse_timestamp_ordering(params))

    def partial_update(self, request, *args, **kwargs):
        variant = self.get_object()

        serializer = ManagerStockItemUpdateSerializer(
            instance=variant,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            ManagerStockItemDetailsSerializer(variant).data,
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
        variant = self.get_object()

        force = str(
            request.query_params.get("force") or request.data.get("force") or ""
        ).strip().lower() in ("1", "true", "yes")

        bill_items_count = variant.bill_items.count()

        if bill_items_count and not force:
            return Response(
                {
                    "requires_confirmation": True,
                    "bill_items_count": bill_items_count,
                    "detail": (
                        f"This item has been used in {bill_items_count} bill(s). "
                        "Deleting will hide it from active stock views. "
                        "Confirm to continue."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        variant.is_active = False
        variant.save(update_fields=["is_active", "updated_at"])

        return Response(
            {"message": "Item deleted successfully."},
            status=status.HTTP_200_OK,
        )


class ManagerStockThresholdViewSet(viewsets.ViewSet):
    permission_classes = [IsManager]
    http_method_names = ["get", "patch"]

    def list(self, request, *args, **kwargs):
        shop = request.user.shop
        return Response(
            {"default_low_stock_limit": shop.default_low_stock_limit},
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        serializer = ManagerStockThresholdSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        shop = request.user.shop
        reset = data.get("reset", False)
        new_default = data.get("default_low_stock_limit")

        with transaction.atomic():
            if new_default is not None:
                shop.default_low_stock_limit = new_default
                shop.save(update_fields=["default_low_stock_limit", "updated_at"])

            default_value = shop.default_low_stock_limit
            updated_count = ProductVariant.objects.filter(is_active=True).update(
                low_stock_threshold=default_value
            )

        return Response(
            {
                "default_low_stock_limit": default_value,
                "updated_products": updated_count,
                "reset": reset,
            },
            status=status.HTTP_200_OK,
        )


class ManagerVendorSummaryViewSet(viewsets.ViewSet):
    permission_classes = [IsManagerOrEmployee]
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        today = timezone.localdate()
        week_end = today + timedelta(days=7)

        pending = StockEntry.objects.filter(is_fully_paid=False)

        total_pending = pending.aggregate(
            amount=Coalesce(
                Sum(
                    F("total_amount") - Coalesce(F("paid_amount"), Decimal("0.00")),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
                Decimal("0.00"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )["amount"]

        pending_bills = pending.count()
        overdue = pending.filter(due_date__isnull=False, due_date__lt=today).count()
        due_this_week = pending.filter(
            due_date__isnull=False,
            due_date__gte=today,
            due_date__lte=week_end,
        ).count()

        return Response(
            {
                "total_pending": format_indian_amount(total_pending),
                "pending_bills": pending_bills,
                "overdue": overdue,
                "due_this_week": due_this_week,
            },
            status=status.HTTP_200_OK,
        )


class ManagerVendorReportViewSet(viewsets.ViewSet):
    permission_classes = [IsManagerOrEmployee]
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        entries, start_date, end_date, _vendor_ids = vendor_report_entries(
            request.query_params
        )
        summary = vendor_report_summary(entries)

        return Response(
            {
                "start_date": start_date.strftime("%d-%m-%Y") if start_date else None,
                "end_date": end_date.strftime("%d-%m-%Y") if end_date else None,
                **summary,
            },
            status=status.HTTP_200_OK,
        )


class ManagerVendorReportPdfViewSet(viewsets.ViewSet):
    permission_classes = [IsManagerOrEmployee]
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        params = request.query_params
        entries, start_date, end_date, _vendor_ids = vendor_report_entries(params)
        groups = vendor_report_payable_groups(entries)

        if start_date and end_date:
            period_label = (
                f"{start_date.strftime('%d-%m-%Y')} – {end_date.strftime('%d-%m-%Y')}"
            )
        elif start_date:
            period_label = f"From {start_date.strftime('%d-%m-%Y')}"
        elif end_date:
            period_label = f"Until {end_date.strftime('%d-%m-%Y')}"
        else:
            period_label = "All dates"

        shop = getattr(request.user, "shop", None)
        business_name = (shop.name if shop else None) or "—"

        pdf_bytes = generate_vendor_report_pdf(
            title="Contacts Payable",
            business_name=business_name,
            period_label=period_label,
            groups=groups,
        )

        filename = "contacts-payable.pdf"
        if start_date and end_date:
            filename = (
                f"contacts-payable-{start_date.strftime('%Y%m%d')}-"
                f"{end_date.strftime('%Y%m%d')}.pdf"
            )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class ManagerVendorBillsViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsManagerOrEmployee]
    serializer_class = ManagerVendorBillSerializer
    pagination_class = ManagerVendorBillsPagination
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        params = self.request.query_params

        search = (params.get("search") or "").strip()
        status_param = (params.get("status") or "").strip().lower()
        start_date_param = (params.get("start_date") or "").strip()
        end_date_param = (params.get("end_date") or "").strip()
        sort = (params.get("sort") or "").strip().lower()

        queryset = (
            StockEntry.objects.select_related("vendor")
            .prefetch_related(
                Prefetch(
                    "stock_variants",
                    queryset=ProductVariant.objects.select_related(
                        "product", "product__item_type", "product__company"
                    ),
                ),
                Prefetch(
                    "top_ups",
                    queryset=StockEntryTopUp.objects.select_related(
                        "product_variant__product",
                        "product_variant__product__item_type",
                        "product_variant__product__company",
                    ),
                ),
            )
        )

        if search:
            queryset = queryset.filter(vendor__name__icontains=search)

        if status_param:
            valid_status = {choice.value for choice in StockEntry.StatusChoices}
            if status_param not in valid_status:
                raise ValidationError(
                    {"status": [f"Invalid status. Choose from {sorted(valid_status)}."]}
                )
            queryset = queryset.filter(status=status_param)

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

        ordering = "created_at" if sort == "oldest" else "-created_at"
        return queryset.order_by(ordering)

    def partial_update(self, request, *args, **kwargs):
        entry = self.get_object()

        serializer = ManagerVendorBillPaymentSerializer(
            data=request.data,
            context={"entry": entry},
        )
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]
        paid = entry.paid_amount or Decimal("0.00")

        with transaction.atomic():
            entry.paid_amount = paid + amount
            entry.save()

        return Response(
            {
                "message": "Payment recorded successfully.",
                "bill": ManagerVendorBillSerializer(entry).data,
            },
            status=status.HTTP_200_OK,
        )


class ManagerVendorBillsBulkPayViewSet(viewsets.ViewSet):
    """
    Allocate one lump-sum payment across selected vendor bills.

    Allocation policy is owned by the backend (currently oldest-first).
    """

    permission_classes = [IsManagerOrEmployee]
    http_method_names = ["post"]

    def create(self, request, *args, **kwargs):
        serializer = ManagerVendorBillsBulkPaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bill_ids = serializer.validated_data["bill_ids"]
        amount = serializer.validated_data["amount"]

        with transaction.atomic():
            entries = list(
                StockEntry.objects.select_for_update()
                .select_related("vendor")
                .filter(id__in=bill_ids)
            )

            found_ids = {entry.id for entry in entries}
            missing = [bill_id for bill_id in bill_ids if bill_id not in found_ids]
            if missing:
                raise ValidationError(
                    {"bill_ids": [f"Unknown bill id(s): {missing}."]}
                )

            vendor_ids = {entry.vendor_id for entry in entries}
            if len(vendor_ids) > 1:
                raise ValidationError(
                    {"bill_ids": ["All selected bills must belong to one vendor."]}
                )

            open_entries = []
            for entry in entries:
                if entry.is_fully_paid or entry.status == StockEntry.StatusChoices.PAID:
                    raise ValidationError(
                        {
                            "bill_ids": [
                                f"Bill {entry.stk_number} is already fully paid."
                            ]
                        }
                    )
                open_entries.append(entry)

            # Backend allocation: oldest open bill first.
            open_entries.sort(key=lambda e: (e.created_at, e.id))

            total_pending = Decimal("0.00")
            for entry in open_entries:
                pending = (entry.total_amount or Decimal("0.00")) - (
                    entry.paid_amount or Decimal("0.00")
                )
                if pending <= 0:
                    raise ValidationError(
                        {
                            "bill_ids": [
                                f"Bill {entry.stk_number} has no pending balance."
                            ]
                        }
                    )
                total_pending += pending

            if amount > total_pending:
                raise ValidationError(
                    {
                        "amount": [
                            "Amount cannot exceed selected pending total "
                            f"({format_indian_amount(total_pending)})."
                        ]
                    }
                )

            remaining = amount
            allocations = []
            updated_entries = []

            for entry in open_entries:
                if remaining <= 0:
                    break

                pending = (entry.total_amount or Decimal("0.00")) - (
                    entry.paid_amount or Decimal("0.00")
                )
                applied = min(remaining, pending)
                if applied <= 0:
                    continue

                paid = entry.paid_amount or Decimal("0.00")
                entry.paid_amount = paid + applied
                entry.save()

                remaining -= applied
                allocations.append(
                    {
                        "bill_id": entry.id,
                        "applied": format_indian_amount(applied),
                        "status": entry.get_status_display(),
                    }
                )
                updated_entries.append(entry)

        refreshed = (
            StockEntry.objects.select_related("vendor")
            .prefetch_related(
                Prefetch(
                    "stock_variants",
                    queryset=ProductVariant.objects.select_related(
                        "product", "product__item_type", "product__company"
                    ),
                ),
                Prefetch(
                    "top_ups",
                    queryset=StockEntryTopUp.objects.select_related(
                        "product_variant__product",
                        "product_variant__product__item_type",
                        "product_variant__product__company",
                    ),
                ),
            )
            .filter(id__in=[entry.id for entry in updated_entries])
        )
        bills_by_id = {entry.id: entry for entry in refreshed}
        ordered_bills = [
            bills_by_id[entry.id]
            for entry in updated_entries
            if entry.id in bills_by_id
        ]

        return Response(
            {
                "message": "Payment allocated successfully.",
                "allocations": allocations,
                "bills": ManagerVendorBillSerializer(ordered_bills, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
