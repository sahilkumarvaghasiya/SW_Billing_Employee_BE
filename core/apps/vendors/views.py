from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction, IntegrityError
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from django.db.models import (
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    Min,
    Prefetch,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import IsEmployee, IsEmployeeWithFeature
from apps.manager.permissions import IsManager, IsManagerOrEmployeeWithFeature
from apps.manager.serializers import ManagerVendorBillSerializer
from apps.manager.services.vendor_report_pdf import generate_vendor_report_pdf
from apps.manager.vendor_report import (
    vendor_report_entries,
    vendor_report_payable_groups,
    vendor_report_summary,
)
from apps.products.models import Color, ItemType, Product, ProductVariant, Size, Company
from apps.products.pagination import ProductPagination
from apps.products.serializers import (
    ProductVariantDetailSerializer,
    ProductVariantListSerializer,
)
from apps.sales.utils import format_indian_amount
from apps.vendors.models import (
    StockEntry,
    StockEntryTopUp,
    Vendor,
    VendorPayment,
    VendorPaymentAllocation,
)
from apps.vendors.paginations import (
    VendorListPagination,
    VendorPayablePendingBillsPagination,
    VendorPayableStatementPagination,
    VendorPayableVendorsPagination,
    VendorStockHistoryPagination,
)
from apps.vendors.serializers import (
    GenerateBarcodeRequestSerializer,
    VendorPayableInfoSerializer,
    VendorPayablePaySerializer,
    VendorPayableVendorSerializer,
    VendorPaymentDetailSerializer,
    VendorStockCreateSerializer,
    VendorExistingStockCreateSerializer,
    VendorListSerializer,
    VendorValidationSerializer,
)
from apps.vendors.utils import (
    build_barcode_number,
    generate_1d_barcode_image,
    normalize_gender,
    relative_media_path,
)

def resolve_name_or_id(model_class, raw_value, field_name="field"):
    """
    Supports:
    - int → ID lookup
    - string → value (create if not exists)
    """

    if isinstance(raw_value, bool):
        raise ValidationError({field_name: "Invalid value."})

    if isinstance(raw_value, int):
        obj = model_class.objects.filter(id=raw_value).first()
        if not obj:
            raise ValidationError({field_name: "Selected item does not exist."})
        return obj

    value = str(raw_value or "").strip()
    if not value:
        raise ValidationError({field_name: "This field is required."})

    obj, _ = model_class.objects.get_or_create(
        name=value.lower(),
    )
    return obj


def update_existing_product(product_data, stock_entry):
    """Top up quantity (and optionally price/purchase price) of existing variants.

    Existing products are not re-created. Each variant is located by its
    ProductVariant id; its quantity is incremented by the submitted pieces and
    price / purchase price are updated only when provided.
    """
    updated_variants = []
    product = None

    for variant in product_data["item_variants"]:
        variant_id = variant.get("variant_id")
        existing = ProductVariant.objects.filter(id=variant_id, is_active=True).first()
        if not existing:
            raise ValidationError(
                {"variant_id": f"Product variant {variant_id} does not exist."}
            )

        existing.quantity = (existing.quantity or 0) + variant["pieces"]

        update_fields = ["quantity"]
        if variant.get("sellprice") is not None:
            existing.price = variant["sellprice"]
            update_fields.append("price")
        if variant.get("purchase_price") is not None:
            existing.original_purchase_price = variant["purchase_price"]
            update_fields.append("original_purchase_price")

        existing.save(update_fields=update_fields)

        StockEntryTopUp.objects.create(
            stock_entry=stock_entry,
            product_variant=existing,
            quantity_added=variant["pieces"],
            purchase_price=variant.get("purchase_price"),
            sell_price=variant.get("sellprice"),
        )

        updated_variants.append(existing)
        product = existing.product

    return {
        "company_name": product.company.name if product and product.company else None,
        "product_type": product.item_type.name if product and product.item_type else None,
        "gender": product.gender if product else None,
        "barcode_number": updated_variants[0].barcode_number if updated_variants else None,
        "barcode_url": None,
        "variant_count": len(updated_variants),
        "is_existing": True,
    }

class GenerateBarcodeViewSet(viewsets.ModelViewSet):
    queryset = StockEntry.objects.none()
    serializer_class = GenerateBarcodeRequestSerializer
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "stock"
    http_method_names = ["post"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        barcode_number = build_barcode_number(request.user.shop_id)
        image_path = generate_1d_barcode_image(barcode_number)
        barcode_url = request.build_absolute_uri(default_storage.url(image_path))

        return Response(
            {
                "barcode_number": barcode_number,
                "barcode_url": barcode_url,
            },
            status=status.HTTP_200_OK,
        )

class ScanExistingProductViewSet(viewsets.ViewSet):
    """Look up a product variant by its barcode/QR number.

    Used by the stock-entry flow: employee scans a product's QR; if a variant
    with that barcode exists we return the same payload as the product detail
    API so the UI can pre-fill and let the user top up its quantity.
    """

    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "stock"
    http_method_names = ["get"]

    def retrieve(self, request, *args, **kwargs):
        barcode_number = (kwargs.get("barcode_number") or "").strip()
        if not barcode_number:
            raise ValidationError({"barcode_number": "Barcode number is required."})

        variant = (
            ProductVariant.objects.select_related(
                "product", "size", "color", "product__item_type", "product__company"
            )
            .filter(barcode_number=barcode_number, is_active=True)
            .order_by("-created_at")
            .first()
        )

        if not variant:
            return Response(
                {"message": "QR code not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProductVariantDetailSerializer(variant, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class VendorExistingProductsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Stock-entry Existing tab: products previously received from this vendor.
    Search by product name (item type), brand (company), or barcode.
    """

    serializer_class = ProductVariantListSerializer
    pagination_class = ProductPagination
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "stock"
    http_method_names = ["get"]

    def get_queryset(self):
        vendor_id = self.kwargs.get("id")
        get_object_or_404(Vendor, id=vendor_id, is_active=True)

        queryset = (
            ProductVariant.objects.select_related(
                "product",
                "size",
                "color",
                "product__item_type",
                "product__company",
            )
            .filter(is_active=True)
            .filter(
                Q(stock_entry__vendor_id=vendor_id)
                | Q(stock_top_ups__stock_entry__vendor_id=vendor_id)
            )
            .distinct()
            .order_by("-created_at")
        )

        search = (self.request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(product__item_type__name__icontains=search)
                | Q(product__company__name__icontains=search)
                | Q(barcode_number__icontains=search)
            )
        return queryset


class VendorStockCreateViewSet(viewsets.ModelViewSet):
    queryset = StockEntry.objects.none()
    serializer_class = VendorStockCreateSerializer
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "stock"
    http_method_names = ["post"]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        vendor = self._get_or_create_vendor(data)

        stock_entry = StockEntry.objects.create(
            vendor=vendor,
            total_amount=data["total_amount"],
            paid_amount=data["paid_amount"],
            due_date=data.get("paymentdeadlinedate"),
            notes=data.get("notes") or "",
            gst = data.get("gst") or 0
        )

        products = self._create_products(
            data["products"], stock_entry, request
        )

        return Response(
            {
                "message": "Stock entry created successfully.",
                "stock_entry_id": stock_entry.id,
                "stk_number": stock_entry.stk_number,
                "status": stock_entry.status,
                "total_amount": str(stock_entry.total_amount),
                "paid_amount": str(stock_entry.paid_amount),
                "paymentdeadlinedate": str(stock_entry.due_date) if stock_entry.due_date else None,
                "products": products,
            },
            status=status.HTTP_201_CREATED,
        )

    
    def _get_or_create_vendor(self, data):
        vendor_name = data["vendor_name"].strip().lower()
        vendor_phone = (data.get("phone") or "").strip()
        vendor_email = (data.get("email") or "").strip().lower() or None
        vendor_gst = (data.get("gst_number") or "").strip() or None
        vendor_address = (data.get("vendor_address") or "").strip()

        try:
            existing_vendor = Vendor.objects.filter(
                phone__iexact=vendor_phone,
            ).first()
            if existing_vendor:
                raise ValidationError({"vendor": "Vendor already exists."})

            return Vendor.objects.create(
                name=vendor_name,
                phone=vendor_phone,
                email=vendor_email,
                gst_number=vendor_gst,
                address=vendor_address,
                is_active=True,
            )

        except IntegrityError:
            raise ValidationError({"vendor": "Vendor already exists."})

   
    def _create_products(self, products, stock_entry, request):
        result = []

        for product_data in products:
            if product_data.get("is_existing"):
                result.append(update_existing_product(product_data, stock_entry))
                continue

            gender = normalize_gender(product_data["gender"])

            item_type = resolve_name_or_id(
                ItemType, product_data["product_type"], "product_type"
            )

            company = None
            company_value = product_data.get("company_name")
            if company_value not in [None, ""]:
                company = resolve_name_or_id(
                    Company,
                    company_value,
                    "company_name",
                )

            product = Product.objects.create(
                company=company,
                gender=gender,
                item_type=item_type,
                is_active=True,
            )

            barcode_number = product_data["barcode_number"]
            barcode_url = product_data.get("barcode_url")

            if not barcode_url:
                image_path = generate_1d_barcode_image(barcode_number)
                barcode_url = request.build_absolute_uri(
                    default_storage.url(image_path)
                )
                image_db_path = image_path
            else:
                image_db_path = relative_media_path(barcode_url)

            variants_to_create = []

            for variant in product_data["item_variants"]:
                size = resolve_name_or_id(Size, variant["size"], "size")
                colour_value = variant.get("colour")
                color = (
                    resolve_name_or_id(Color, colour_value, "colour")
                    if colour_value not in (None, "")
                    else None
                )

                variants_to_create.append(
                    ProductVariant(
                        product=product,
                        stock_entry=stock_entry,
                        barcode_number=barcode_number,
                        barcode_image=image_db_path,
                        size=size,
                        color=color,
                        original_purchase_price=variant["purchase_price"],
                        price=variant["sellprice"],
                        quantity=variant["pieces"],
                        is_active=True,
                    )
                )

            ProductVariant.objects.bulk_create(variants_to_create)

            result.append(
                {
                    "company_name": product.company.name if product.company else None,
                    "product_type": product.item_type.name,
                    "gender": gender,
                    "barcode_number": barcode_number,
                    "barcode_url": barcode_url,
                    "variant_count": len(variants_to_create),
                }
            )

        return result

class VendorExistingStockCreateViewSet(viewsets.ModelViewSet):
    queryset = StockEntry.objects.none()
    serializer_class = VendorExistingStockCreateSerializer
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "stock"
    http_method_names = ["post"]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        vendor_id = kwargs.get("id")

        if not vendor_id:
            raise ValidationError({"vendor": "Vendor is required."})

        vendor = get_object_or_404(Vendor, id=vendor_id)


        stock_entry = StockEntry.objects.create(
            vendor=vendor,
            total_amount=data["total_amount"],
            paid_amount=data["paid_amount"],
            due_date=data.get("paymentdeadlinedate"),
            notes=data.get("notes") or "",
            gst = data.get("gst") or 0
        )

        products = self._create_products(
            data["products"], stock_entry, request
        )

        return Response(
            {
                "message": "Stock entry created for existing vendor.",
                "vendor_id": vendor.id,
                "stock_entry_id": stock_entry.id,
                "stk_number": stock_entry.stk_number,
                "status": stock_entry.status,
                "total_amount": str(stock_entry.total_amount),
                "paid_amount": str(stock_entry.paid_amount),
                "paymentdeadlinedate": str(stock_entry.due_date) if stock_entry.due_date else None,
                "products": products,
            },
            status=status.HTTP_201_CREATED,
        )

    def _create_products(self, products, stock_entry, request):
        result = []

        for product_data in products:
            if product_data.get("is_existing"):
                result.append(update_existing_product(product_data, stock_entry))
                continue

            gender = normalize_gender(product_data["gender"])

            item_type = resolve_name_or_id(
                ItemType, product_data["product_type"], "product_type"
            )

            company = None
            company_value = product_data.get("company_name")

            if company_value not in [None, ""]:
                company = resolve_name_or_id(
                    Company,
                    company_value,
                    "company_name",
                )

            product = Product.objects.create(
                company=company,
                gender=gender,
                item_type=item_type,
                is_active=True,
            )

            barcode_number = product_data["barcode_number"]
            barcode_url = product_data.get("barcode_url")

            if not barcode_url:
                image_path = generate_1d_barcode_image(barcode_number)
                barcode_url = request.build_absolute_uri(
                    default_storage.url(image_path)
                )
                image_db_path = image_path
            else:
                image_db_path = relative_media_path(barcode_url)

            variants_to_create = []

            for variant in product_data["item_variants"]:
                size = resolve_name_or_id(Size, variant["size"], "size")
                colour_value = variant.get("colour")
                color = (
                    resolve_name_or_id(Color, colour_value, "colour")
                    if colour_value not in (None, "")
                    else None
                )

                variants_to_create.append(
                    ProductVariant(
                        product=product,
                        stock_entry=stock_entry,
                        barcode_number=barcode_number,
                        barcode_image=image_db_path,
                        size=size,
                        color=color,
                        original_purchase_price=variant["purchase_price"],
                        price=variant["sellprice"],
                        quantity=variant["pieces"],
                        is_active=True,
                    )
                )

            ProductVariant.objects.bulk_create(variants_to_create)

            result.append(
                {
                    "company_name": product.company.name if product.company else None,
                    "product_type": product.item_type.name,
                    "gender": gender,
                    "barcode_number": barcode_number,
                    "barcode_url": barcode_url,
                    "variant_count": len(variants_to_create),
                }
            )

        return result


class VendorListViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VendorListSerializer
    permission_classes = [IsManagerOrEmployeeWithFeature]
    feature_access_key = "stock"
    pagination_class = VendorListPagination
    http_method_names = ["get"]

    def get_queryset(self):
        search = (self.request.query_params.get("search") or "").strip()

        queryset = Vendor.objects.filter(is_active=True)

        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(phone__icontains=search))

        return queryset.order_by("-created_at")


class VendorValidationViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.none()
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "stock"
    http_method_names = ["post"]

    def create(self, request, *args, **kwargs):
        serializer = VendorValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        phone = data["phone"].strip()
        email = data.get("email")
        gst_number = data.get("gst_number")

        match_query = Q(phone__iexact=phone)
        if email:
            match_query |= Q(email__iexact=email)
        if gst_number:
            match_query |= Q(gst_number__iexact=gst_number)

        vendor = Vendor.objects.filter(match_query).first()

        if vendor:
            return Response(
                {
                    "exists": True,
                    "message": f"Vendor already exists. Use existing vendor list",
                    "vendor": {
                        "id": vendor.id,
                        "name": vendor.name,
                        "phone": vendor.phone,
                        "email": vendor.email,
                        "gst_number": vendor.gst_number,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {"exists": False, "message": "Vendor is available."},
            status=status.HTTP_200_OK,
        )



class VendorStockHistoryListViewset(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "stock"
    http_method_names = ["get"]
    pagination_class = VendorStockHistoryPagination

    def list(self, request, *args, **kwargs):
        vendor_id = kwargs.get("id")
        if not vendor_id:
            return Response(
                {"message": ["Vendor id path parameter is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vendor = get_object_or_404(Vendor, id=vendor_id)

        queryset = StockEntry.objects.filter(vendor=vendor)

        status_filter = request.query_params.get("status")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        parsed_start_date = None
        parsed_end_date = None

        if start_date:
            try:
                parsed_start_date = datetime.strptime(start_date, "%d-%m-%Y").date()
            except ValueError:
                return Response(
                    {"message": ["Invalid start_date. Expected format is DD-MM-YYYY."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if end_date:
            try:
                parsed_end_date = datetime.strptime(end_date, "%d-%m-%Y").date()
            except ValueError:
                return Response(
                    {"message": ["Invalid end_date. Expected format is DD-MM-YYYY."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if parsed_start_date and parsed_end_date and parsed_start_date > parsed_end_date:
            return Response(
                {"message": ["start_date cannot be greater than end_date."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if status_filter == StockEntry.StatusChoices.PAID:
            queryset = queryset.filter(status=StockEntry.StatusChoices.PAID, is_fully_paid=True)
        elif status_filter == StockEntry.StatusChoices.PARTIAL:
            queryset = queryset.filter(status=StockEntry.StatusChoices.PARTIAL, is_fully_paid=False)
        else:
            queryset = queryset.filter(status=StockEntry.StatusChoices.UNPAID, is_fully_paid=False)

   
        if parsed_start_date:
            queryset = queryset.filter(created_at__date__gte=parsed_start_date)
        if parsed_end_date:
            queryset = queryset.filter(created_at__date__lte=parsed_end_date)

        queryset = queryset.order_by("-created_at")

        page = self.paginate_queryset(queryset)
        entries = page if page is not None else queryset

        data = [
            {
                "id": entry.id,
                "stk_number": entry.stk_number,
                "created_date": entry.created_at.strftime("%d-%m-%Y"),
                "total_amount": format_indian_amount(entry.total_amount),
                "paid_amount": format_indian_amount(entry.paid_amount),
                "pending_amount": format_indian_amount(max(entry.total_amount - entry.paid_amount, 0)),
                "gst": f"{entry.gst:.2f}%",
                "status": entry.status,
            }
            for entry in entries
        ]

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data, status=status.HTTP_200_OK)


class VendorStockHistoryDetailsViewset(viewsets.ReadOnlyModelViewSet):
    """Return detailed stock entry information for a given stk_number.

    Query params:
      - stk_number (required): invoice number string

    Response includes invoice metadata, totals, vendor info and a list of
    products with their variants.
    """
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "stock"
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        stk_number = request.query_params.get("stk_number")
        if not stk_number:
            return Response(
                {"message": ["stk_number query parameter is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stock_entry = get_object_or_404(StockEntry, stk_number=stk_number)

        variants_qs = (
            stock_entry.stock_variants.select_related("product", "product__item_type", "size", "color").order_by("-created_at")
        )

        products = {}
        for v in variants_qs:
            p = v.product
            pid = p.id
            if pid not in products:
                products[pid] = {
                    "product_name": p.item_type.name if p.item_type else None,
                    "company_name": p.company.name if p.company else None,
                    "gender": p.gender,
                    "variants": [],
                }

            products[pid]["variants"].append(
                {
                    "size": v.size.name if v.size else None,
                    "color": v.color.name if v.color else None,
                    "actual_price": v.original_purchase_price,
                    "quantity": v.quantity,
                    "is_existing": False,
                }
            )
        top_ups_qs = (
            stock_entry.top_ups.select_related(
                "product_variant",
                "product_variant__product",
                "product_variant__product__item_type",
                "product_variant__product__company",
                "product_variant__size",
                "product_variant__color",
            ).order_by("-created_at")
        )

        for top_up in top_ups_qs:
            v = top_up.product_variant
            p = v.product
            pid = p.id
            if pid not in products:
                products[pid] = {
                    "product_name": p.item_type.name if p.item_type else None,
                    "company_name": p.company.name if p.company else None,
                    "gender": p.gender,
                    "variants": [],
                }

            products[pid]["variants"].append(
                {
                    "size": v.size.name if v.size else None,
                    "color": v.color.name if v.color else None,
                    "actual_price": (
                        top_up.purchase_price
                        if top_up.purchase_price is not None
                        else v.original_purchase_price
                    ),
                    "quantity": top_up.quantity_added,
                    "is_existing": True,
                }
            )

        response = {
            "stk_number": stock_entry.stk_number,
            "created_date": stock_entry.created_at.strftime("%d-%m-%Y"),
            "vendor_name": stock_entry.vendor.name,
            "total_amount": format_indian_amount(stock_entry.total_amount),
            "paid_amount": format_indian_amount(stock_entry.paid_amount),
            "pending_amount": format_indian_amount(
                max(stock_entry.total_amount - stock_entry.paid_amount, 0)
            ),
            "payment_deadline": stock_entry.due_date.strftime("%d-%m-%Y") if stock_entry.due_date else None,
            "status": stock_entry.status,
            "products": list(products.values()),
        }

        return Response(response, status=status.HTTP_200_OK)


class VendorPayableSummaryViewSet(viewsets.ModelViewSet):
    """Employee Payable hub summary: open bills, overdue, due soon (.env window)."""

    queryset = StockEntry.objects.none()
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        today = timezone.localdate()
        alert_before_days = max(
            int(getattr(settings, "VENDOR_DUE_ALERT_DAYS_BEFORE", 5)),
            0,
        )
        due_soon_end = today + timedelta(days=alert_before_days)

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
        due_soon = pending.filter(
            due_date__isnull=False,
            due_date__gte=today,
            due_date__lte=due_soon_end,
        ).count()

        return Response(
            {
                "total_pending": format_indian_amount(total_pending),
                "pending_bills": pending_bills,
                "overdue": overdue,
                "due_soon": due_soon,
            },
            status=status.HTTP_200_OK,
        )


class VendorPayableVendorsViewSet(viewsets.ModelViewSet):
    """
    Employee Payable vendor list.
    Search by name. Pending vendors first (nearest due date), settled last.
    """

    serializer_class = VendorPayableVendorSerializer
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["get"]
    pagination_class = VendorPayableVendorsPagination

    def get_queryset(self):
        today = timezone.localdate()
        search = (self.request.query_params.get("search") or "").strip()

        pending_filter = Q(stock_entries__is_fully_paid=False)
        overdue_filter = pending_filter & Q(
            stock_entries__due_date__isnull=False,
            stock_entries__due_date__lt=today,
        )
        pending_amount = ExpressionWrapper(
            F("stock_entries__total_amount")
            - Coalesce(F("stock_entries__paid_amount"), Value(Decimal("0.00"))),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )

        queryset = (
            Vendor.objects.filter(is_active=True)
            .annotate(
                entry_count=Count("stock_entries", distinct=True),
                bills_count=Count(
                    "stock_entries",
                    filter=pending_filter,
                    distinct=True,
                ),
                overdue_count=Count(
                    "stock_entries",
                    filter=overdue_filter,
                    distinct=True,
                ),
                total_pending=Coalesce(
                    Sum(
                        pending_amount,
                        filter=pending_filter,
                    ),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
                nearest_due_date=Min(
                    "stock_entries__due_date",
                    filter=pending_filter & Q(stock_entries__due_date__isnull=False),
                ),
            )
            .filter(entry_count__gt=0)
        )

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.annotate(
            sort_group=Case(
                When(total_pending__gt=0, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by(
            "sort_group",
            F("nearest_due_date").asc(nulls_last=True),
            "name",
        )


def _payable_pending_amount_annotation():
    return Coalesce(
        Sum(
            ExpressionWrapper(
                F("stock_entries__total_amount")
                - Coalesce(F("stock_entries__paid_amount"), Value(Decimal("0.00"))),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            filter=Q(stock_entries__is_fully_paid=False),
        ),
        Value(Decimal("0.00")),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def _payable_bill_queryset():
    return (
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


class VendorPayableInfoViewSet(viewsets.ModelViewSet):
    """Employee Payable vendor Info tab."""

    serializer_class = VendorPayableInfoSerializer
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["get"]
    lookup_field = "id"

    def get_queryset(self):
        return Vendor.objects.filter(is_active=True).annotate(
            total_pending=_payable_pending_amount_annotation(),
        )

    def retrieve(self, request, *args, **kwargs):
        vendor = self.get_object()
        return Response(
            self.get_serializer(vendor).data,
            status=status.HTTP_200_OK,
        )


class VendorPayablePendingBillsViewSet(viewsets.ModelViewSet):
    """
    Employee Payable Pending tab for one vendor.
    Optional start_date / end_date (DD-MM-YYYY) on bill date.
    Ordered by nearest due date first.
    """

    serializer_class = ManagerVendorBillSerializer
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["get"]
    pagination_class = VendorPayablePendingBillsPagination

    def get_queryset(self):
        vendor_id = self.kwargs.get("id")
        get_object_or_404(Vendor, id=vendor_id, is_active=True)

        params = self.request.query_params
        start_date_param = (params.get("start_date") or "").strip()
        end_date_param = (params.get("end_date") or "").strip()

        queryset = _payable_bill_queryset().filter(
            vendor_id=vendor_id,
            is_fully_paid=False,
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

        return queryset.order_by(
            F("due_date").asc(nulls_last=True),
            "created_at",
        )


class VendorPayableBillDetailViewSet(viewsets.ModelViewSet):
    """Employee Payable bill details (Pending → Details)."""

    serializer_class = ManagerVendorBillSerializer
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["get"]
    lookup_field = "id"

    def get_queryset(self):
        return _payable_bill_queryset()


class VendorPayablePayViewSet(viewsets.ModelViewSet):
    """
    Allocate across selected bills:

    Sort: smallest pending first; if same pending, nearest due date
    (null due last), then created_at, then id.

    Example order: 1000/due14, 2000/due10, 3000/due5, 1000/due10
    → clear 1000/due10, then 1000/due14, then 2000, then 3000.

    1) paid amount (cash) → clears bills waterfall
    2) optional discount (−) → clears extra pending after cash
    3) optional surcharge (+) → added on last bill in that sort order
    """

    queryset = VendorPayment.objects.none()
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["post"]

    def create(self, request, *args, **kwargs):
        vendor = get_object_or_404(Vendor, id=kwargs.get("id"), is_active=True)
        serializer = VendorPayablePaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        bill_ids = data["bill_ids"]
        amount = data["amount"]
        discount = data.get("discount") or Decimal("0.00")
        surcharge = data.get("surcharge") or Decimal("0.00")
        payment_date = data.get("payment_date") or timezone.localdate()

        if discount > 0 and surcharge > 0:
            raise ValidationError(
                {"non_field_errors": ["Use either discount or surcharge, not both."]}
            )

        with transaction.atomic():
            entries = list(
                StockEntry.objects.select_for_update()
                .select_related("vendor")
                .filter(id__in=bill_ids, vendor_id=vendor.id)
            )

            found_ids = {entry.id for entry in entries}
            missing = [bill_id for bill_id in bill_ids if bill_id not in found_ids]
            if missing:
                raise ValidationError(
                    {"bill_ids": [f"Unknown bill id(s) for this vendor: {missing}."]}
                )

            open_entries = []
            total_pending = Decimal("0.00")
            for entry in entries:
                if entry.is_fully_paid or entry.status == StockEntry.StatusChoices.PAID:
                    raise ValidationError(
                        {
                            "bill_ids": [
                                f"Bill {entry.stk_number} is already fully paid."
                            ]
                        }
                    )
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
                open_entries.append(entry)

            if amount > total_pending:
                raise ValidationError(
                    {
                        "amount": [
                            "Amount cannot exceed selected pending "
                            f"({format_indian_amount(total_pending)})."
                        ]
                    }
                )
            if discount > total_pending:
                raise ValidationError(
                    {
                        "discount": [
                            "Discount cannot exceed selected pending "
                            f"({format_indian_amount(total_pending)})."
                        ]
                    }
                )
            if amount + discount > total_pending:
                raise ValidationError(
                    {
                        "amount": [
                            "Paid + discount cannot exceed selected pending "
                            f"({format_indian_amount(total_pending)})."
                        ]
                    }
                )

            # Minimum pending first; same pending → nearest due date.
            open_entries.sort(
                key=lambda e: (
                    (e.total_amount or Decimal("0.00"))
                    - (e.paid_amount or Decimal("0.00")),
                    e.due_date is None,
                    e.due_date or timezone.localdate(),
                    e.created_at,
                    e.id,
                )
            )

            payment = VendorPayment.objects.create(
                vendor=vendor,
                amount=amount,
                discount=discount,
                surcharge=surcharge,
                payment_date=payment_date,
            )

            allocation_totals = {entry.id: Decimal("0.00") for entry in open_entries}
            updated_ids = set()

            def _apply_chunk(budget):
                remaining = budget
                if remaining <= 0:
                    return
                for entry in open_entries:
                    if remaining <= 0:
                        break
                    pending = (entry.total_amount or Decimal("0.00")) - (
                        entry.paid_amount or Decimal("0.00")
                    )
                    applied = min(remaining, pending)
                    if applied <= 0:
                        continue
                    entry.paid_amount = (entry.paid_amount or Decimal("0.00")) + applied
                    entry.save()
                    allocation_totals[entry.id] += applied
                    updated_ids.add(entry.id)
                    remaining -= applied

            # Cash + discount clear bills (−).
            _apply_chunk(amount)
            _apply_chunk(discount)

            # Surcharge (+): increase last selected bill's total (adds pending).
            if surcharge > 0 and open_entries:
                last_bill = open_entries[-1]
                last_bill.total_amount = (
                    last_bill.total_amount or Decimal("0.00")
                ) + surcharge
                last_bill.save()
                updated_ids.add(last_bill.id)

            for entry in open_entries:
                applied = allocation_totals.get(entry.id) or Decimal("0.00")
                if applied <= 0:
                    continue
                VendorPaymentAllocation.objects.create(
                    payment=payment,
                    stock_entry=entry,
                    applied_amount=applied,
                )

        payment = (
            VendorPayment.objects.select_related("vendor")
            .prefetch_related("allocations__stock_entry")
            .get(id=payment.id)
        )
        bills = ManagerVendorBillSerializer(
            _payable_bill_queryset().filter(id__in=list(updated_ids)),
            many=True,
        ).data

        return Response(
            {
                "message": "Payment allocated successfully.",
                "payment": VendorPaymentDetailSerializer(payment).data,
                "bills": bills,
            },
            status=status.HTTP_201_CREATED,
        )


class VendorPayableStatementViewSet(viewsets.ModelViewSet):
    """Vendor statement: purchases + persisted payments (newest first)."""

    queryset = Vendor.objects.none()
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["get"]
    pagination_class = VendorPayableStatementPagination

    def list(self, request, *args, **kwargs):
        vendor = get_object_or_404(Vendor, id=kwargs.get("id"), is_active=True)
        params = request.query_params
        start_date_param = (params.get("start_date") or "").strip()
        end_date_param = (params.get("end_date") or "").strip()

        start_date = None
        end_date = None
        if start_date_param:
            try:
                start_date = datetime.strptime(start_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError(
                    {"start_date": ["Invalid date format. Use DD-MM-YYYY."]}
                ) from exc
        if end_date_param:
            try:
                end_date = datetime.strptime(end_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError(
                    {"end_date": ["Invalid date format. Use DD-MM-YYYY."]}
                ) from exc

        bills_qs = _payable_bill_queryset().filter(vendor_id=vendor.id)
        payments_qs = (
            VendorPayment.objects.filter(vendor_id=vendor.id)
            .prefetch_related("allocations__stock_entry")
            .order_by("-payment_date", "-created_at")
        )

        if start_date:
            bills_qs = bills_qs.filter(created_at__date__gte=start_date)
            payments_qs = payments_qs.filter(payment_date__gte=start_date)
        if end_date:
            bills_qs = bills_qs.filter(created_at__date__lte=end_date)
            payments_qs = payments_qs.filter(payment_date__lte=end_date)

        results = []
        for bill in bills_qs.order_by("-created_at"):
            results.append(
                {
                    "kind": "purchase",
                    "sort_at": timezone.localtime(bill.created_at).isoformat(),
                    "bill": ManagerVendorBillSerializer(bill).data,
                }
            )
        for payment in payments_qs:
            results.append(
                {
                    "kind": "payment",
                    "sort_at": timezone.localtime(payment.created_at).isoformat(),
                    "payment": VendorPaymentDetailSerializer(payment).data,
                }
            )

        results.sort(key=lambda row: row["sort_at"], reverse=True)

        page = self.paginate_queryset(results)
        if page is not None:
            return self.get_paginated_response(page)
        return Response({"results": results}, status=status.HTTP_200_OK)


class VendorPayablePaymentDetailViewSet(viewsets.ModelViewSet):
    """Persisted payment details for Statement → Payment tap."""

    serializer_class = VendorPaymentDetailSerializer
    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["get"]
    lookup_field = "id"

    def get_queryset(self):
        return VendorPayment.objects.select_related("vendor").prefetch_related(
            "allocations__stock_entry"
        )


class VendorPayableReportPreviewViewSet(viewsets.ViewSet):
    """
    Employee all-vendor payable report preview.
    Empty start/end → last 6 months through today.
    """

    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        entries, start_date, end_date, _vendor_ids = vendor_report_entries(
            request.query_params, default_last_months=6
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


class VendorPayableReportPdfViewSet(viewsets.ViewSet):
    """
    Employee all-vendor payable report PDF.
    Empty start/end → last 6 months through today.
    """

    permission_classes = [IsEmployeeWithFeature]
    feature_access_key = "payable"
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        entries, start_date, end_date, _vendor_ids = vendor_report_entries(
            request.query_params, default_last_months=6
        )
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
            period_label = "Last 6 months"

        shop = getattr(request.user, "shop", None)
        business_name = (shop.name if shop else None) or "—"

        pdf_bytes = generate_vendor_report_pdf(
            title="Vendor Payable Report",
            business_name=business_name,
            period_label=period_label,
            groups=groups,
        )

        filename = "vendor-payable-report.pdf"
        if start_date and end_date:
            filename = (
                f"vendor-payable-report-{start_date.strftime('%Y%m%d')}-"
                f"{end_date.strftime('%Y%m%d')}.pdf"
            )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response