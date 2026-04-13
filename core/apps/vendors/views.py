from datetime import datetime
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from apps.accounts.permissions import IsEmployee
from apps.products.models import Color, ItemType, Product, ProductVariant, Size
from apps.vendors.models import StockEntry, Vendor
from apps.vendors.serializers import (
    GenerateBarcodeRequestSerializer,
    VendorStockCreateSerializer,
    VendorExistingStockCreateSerializer,
    VendorListSerializer,
)
from apps.vendors.paginations import VendorListPagination, VendorStockHistoryPagination
from apps.vendors.utils import (
    build_barcode_number,
    generate_1d_barcode_image,
    normalize_gender,
    relative_media_path,
)


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

        shop = request.user.shop
        vendor_name = data["vendor_name"].strip().lower()
        vendor_address = (data.get("vendor_address") or "").strip()

        existing_vendor = (
            Vendor.objects.only("id")
            .filter(shop=shop, name=vendor_name)
            .first()
        )

        if existing_vendor:
            return Response(
                {
                    "message": "Vendor already exists. Use existing vendor stock API for this vendor."
                    
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        vendor = Vendor.objects.create(
            shop=shop,
            name=vendor_name,
            address=vendor_address,
            is_active=True,
        )

        stock_entry = StockEntry.objects.create(
            shop=shop,
            vendor=vendor,
            total_amount=data["total_amount"],
            paid_amount=data["paid_amount"],
            due_date=data["paymentdeadlinedate"],
            notes=data.get("notes") or "",
        )

        created_products = []

        for product_data in data["products"]:
            gender = normalize_gender(product_data["gender"])
            item_type, _ = ItemType.objects.get_or_create(
                shop=shop,
                name=product_data["product_type"].strip().lower(),
            )

            product = Product.objects.create(
                shop=shop,
                name=product_data["product_type"],
                company_name=product_data["company_name"],
                gender=gender,
                item_type=item_type,
                is_active=True,
            )

            barcode_number = product_data["barcode_number"]
            barcode_url = product_data.get("barcode_url")

            if not barcode_url:
                image_path = generate_1d_barcode_image(barcode_number)
                barcode_url = request.build_absolute_uri(default_storage.url(image_path))
                image_db_path = image_path
            else:
                image_db_path = relative_media_path(barcode_url)

            for variant_data in product_data["item_variants"]:
                size_obj, _ = Size.objects.get_or_create(
                    shop=shop,
                    name=variant_data["size"].strip().lower(),
                )
                color_obj, _ = Color.objects.get_or_create(
                    shop=shop,
                    name=variant_data["colour"].strip().lower(),
                )

                ProductVariant.objects.create(
                    product=product,
                    stock_entry=stock_entry,
                    qr_code_number=barcode_number,
                    qr_code_image=image_db_path,
                    size=size_obj,
                    color=color_obj,
                    original_price=variant_data["sellprice"],
                    price=variant_data["sellprice"],
                    quantity=variant_data["pieces"],
                    is_active=True,
                )

            created_products.append(
                {
                    "company_name": product_data["company_name"],
                    "product_type": product_data["product_type"],
                    "gender": gender,
                    "barcode_number": barcode_number,
                    "barcode_url": barcode_url,
                    "variant_count": len(product_data["item_variants"]),
                }
            )

        return Response(
            {
                "message": "Stock entry created successfully.",
                "stock_entry_id": stock_entry.id,
                "invoice_number": stock_entry.invoice_number,
                "status": stock_entry.status,
                "total_amount": str(stock_entry.total_amount),
                "paid_amount": str(stock_entry.paid_amount),
                "paymentdeadlinedate": str(stock_entry.due_date),
                "products": created_products,
            },
            status=status.HTTP_201_CREATED,
        )


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
        if vendor_id is None:
            return Response(
                {"message": ["Vendor id path parameter is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shop = request.user.shop
        vendor = get_object_or_404(Vendor, id=vendor_id, shop=shop)

        stock_entry = StockEntry.objects.create(
            shop=shop,
            vendor=vendor,
            total_amount=data["total_amount"],
            paid_amount=data["paid_amount"],
            due_date=data["paymentdeadlinedate"],
            notes=data.get("notes") or "",
        )

        updated_products = []

        for product_data in data["products"]:
            gender = normalize_gender(product_data["gender"])
            item_type, _ = ItemType.objects.get_or_create(
                shop=shop,
                name=product_data["product_type"].strip().lower(),
            )

            product = Product.objects.create(
                shop=shop,
                name=product_data["product_type"],
                company_name=product_data["company_name"],
                gender=gender,
                item_type=item_type,
                is_active=True,
            )

            barcode_number = product_data["barcode_number"]
            barcode_url = product_data.get("barcode_url")

            if not barcode_url:
                image_path = generate_1d_barcode_image(barcode_number)
                barcode_url = request.build_absolute_uri(default_storage.url(image_path))
                image_db_path = image_path
            else:
                image_db_path = relative_media_path(barcode_url)

            for variant_data in product_data["item_variants"]:
                size_obj, _ = Size.objects.get_or_create(
                    shop=shop,
                    name=variant_data["size"].strip().lower(),
                )
                color_obj, _ = Color.objects.get_or_create(
                    shop=shop,
                    name=variant_data["colour"].strip().lower(),
                )

                ProductVariant.objects.create(
                    product=product,
                    stock_entry=stock_entry,
                    qr_code_number=barcode_number,
                    qr_code_image=image_db_path,
                    size=size_obj,
                    color=color_obj,
                    original_price=variant_data["sellprice"],
                    price=variant_data["sellprice"],
                    quantity=variant_data["pieces"],
                    is_active=True,
                )

            updated_products.append(
                {
                    "company_name": product_data["company_name"],
                    "product_type": product_data["product_type"],
                    "gender": gender,
                    "barcode_number": barcode_number,
                    "barcode_url": barcode_url,
                    "variant_count": len(product_data["item_variants"]),
                }
            )

        return Response(
            {
                "message": "New stock entry created for existing vendor.",
                "vendor_id": vendor.id,
                "stock_entry_id": stock_entry.id,
                "invoice_number": stock_entry.invoice_number,
                "status": stock_entry.status,
                "total_amount": str(stock_entry.total_amount),
                "paid_amount": str(stock_entry.paid_amount),
                "paymentdeadlinedate": str(stock_entry.due_date),
                "products": updated_products,
            },
            status=status.HTTP_200_OK,
        )


class VendorListViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VendorListSerializer
    permission_classes = [IsEmployee]
    pagination_class = VendorListPagination
    http_method_names = ["get"]

    def get_queryset(self):
        user = self.request.user
        search = (self.request.query_params.get("search") or "").strip()

        queryset = Vendor.objects.filter(shop=user.shop, is_active=True)

        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(phone__icontains=search))

        return queryset.order_by("-created_at")



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

        shop = request.user.shop
        vendor = get_object_or_404(Vendor, id=vendor_id, shop=shop)

        queryset = StockEntry.objects.filter(shop=shop, vendor=vendor)

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
                "invoice_number": entry.invoice_number,
                "created_date": entry.created_at.strftime("%d-%m-%Y"),
                "total_amount": str(entry.total_amount),
                "paid_amount": str(entry.paid_amount),
                "pending_amount": str(max(entry.total_amount - entry.paid_amount, 0)),
                "status": entry.status,
            }
            for entry in entries
        ]

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data, status=status.HTTP_200_OK)


class VendorStockHistoryDetailsViewset(viewsets.ReadOnlyModelViewSet):
    """Return detailed stock entry information for a given invoice_number.

    Query params:
      - invoice_number (required): invoice number string

    Response includes invoice metadata, totals, vendor info and a list of
    products with their variants.
    """
    permission_classes = [IsEmployee]
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        invoice_number = request.query_params.get("invoice_number")
        if not invoice_number:
            return Response(
                {"message": ["invoice_number query parameter is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        shop = request.user.shop
        stock_entry = get_object_or_404(StockEntry, invoice_number=invoice_number, shop=shop)

        variants_qs = (
            stock_entry.stock_variants.select_related("product", "size", "color").order_by("-created_at")
        )

        products = {}
        for v in variants_qs:
            p = v.product
            pid = p.id
            if pid not in products:
                products[pid] = {
                    "product_name": p.name,
                    "company_name": p.company_name,
                    "gender": p.gender,
                    "variants": [],
                }

            products[pid]["variants"].append(
                {
                    "size": v.size.name,
                    "color": v.color.name,
                    "actual_price": v.original_price,
                    "quantity": v.quantity,
                }
            )

        response = {
            "invoice_number": stock_entry.invoice_number,
            "created_date": stock_entry.created_at.strftime("%d-%m-%Y"),
            "vendor_name": stock_entry.vendor.name,
            "total_amount": str(stock_entry.total_amount),
            "paid_amount": str(stock_entry.paid_amount),
            "pending_amount": str(max(stock_entry.total_amount - stock_entry.paid_amount, 0)),
            "payment_deadline": stock_entry.due_date.strftime("%d-%m-%Y") if stock_entry.due_date else None,
            "status": stock_entry.status,
            "products": list(products.values()),
        }

        return Response(response, status=status.HTTP_200_OK)