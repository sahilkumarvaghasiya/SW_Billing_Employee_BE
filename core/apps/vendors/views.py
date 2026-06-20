from datetime import datetime
from django.core.files.storage import default_storage
from django.db import transaction, IntegrityError
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from apps.accounts.permissions import IsEmployee
from apps.manager.permissions import IsManager
from apps.products.models import Color, ItemType, Product, ProductVariant, Size, Company
from apps.vendors.models import StockEntry, Vendor
from apps.vendors.serializers import (
    GenerateBarcodeRequestSerializer,
    VendorStockCreateSerializer,
    VendorExistingStockCreateSerializer,
    VendorListSerializer,
    VendorValidationSerializer,
)
from apps.vendors.paginations import VendorListPagination, VendorStockHistoryPagination
from apps.vendors.utils import (
    build_barcode_number,
    generate_1d_barcode_image,
    normalize_gender,
    relative_media_path,
)
from django.core.exceptions import ValidationError
from apps.sales.utils import format_indian_amount

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

class GenerateBarcodeViewSet(viewsets.ModelViewSet):
    queryset = StockEntry.objects.none()
    serializer_class = GenerateBarcodeRequestSerializer
    permission_classes = [IsEmployee]
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

class VendorStockCreateViewSet(viewsets.ModelViewSet):
    queryset = StockEntry.objects.none()
    serializer_class = VendorStockCreateSerializer
    permission_classes = [IsEmployee]
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
            due_date=data["paymentdeadlinedate"],
            notes=data.get("notes") or "",
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
                "paymentdeadlinedate": str(stock_entry.due_date),
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
                color = resolve_name_or_id(Color, variant["colour"], "colour")

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
    permission_classes = [IsEmployee]
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
            due_date=data["paymentdeadlinedate"],
            notes=data.get("notes") or "",
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
                "paymentdeadlinedate": str(stock_entry.due_date),
                "products": products,
            },
            status=status.HTTP_201_CREATED,
        )

    def _create_products(self, products, stock_entry, request):
        result = []

        for product_data in products:
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
                color = resolve_name_or_id(Color, variant["colour"], "colour")

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
    permission_classes = [IsEmployee | IsManager]
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
    permission_classes = [IsEmployee]
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
    permission_classes = [IsEmployee]
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
    permission_classes = [IsEmployee]
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
                    "size": v.size.name,
                    "color": v.color.name,
                    "actual_price": v.original_purchase_price,
                    "quantity": v.quantity,
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