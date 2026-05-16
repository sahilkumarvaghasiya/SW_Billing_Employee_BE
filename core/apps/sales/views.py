from decimal import Decimal
from datetime import timedelta
from datetime import datetime
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import status
from django.db.models import Q, Sum
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from apps.accounts.permissions import IsEmployee
from apps.products.models import ProductVariant
from apps.sales.notifications import (
    handle_stock_level_notification,
    purge_expired_notifications,
)
from apps.sales.pagination import SalesBarcodeLookupPagination, SalesHistoryPagination
from apps.sales.models import Bill, BillItem, Customer, Notification, PaymentConfig
from apps.sales.serializers import (
    BillCreateSerializer,
    BarcodeLookupProductSerializer,
    CustomerLookupSerializer,
    NotificationUnreadSerializer,
    PaymentConfigQRListSerializer,
    SalesHistoryDetailSerializer,
    SalesHistoryListSerializer,
)
from apps.sales.utils import format_indian_amount
import os
from apps.sales.services.pdf_service import generate_bill_pdf
from apps.sales.services.whatsapp_service import upload_pdf_to_meta, send_invoice_template_message

class BarcodeProductLookupListView(viewsets.ReadOnlyModelViewSet):
    serializer_class = BarcodeLookupProductSerializer
    permission_classes = [IsEmployee]
    pagination_class = SalesBarcodeLookupPagination

    def get_queryset(self):
        barcode_number = (self.kwargs.get("barcode_number") or "").strip()

        if not barcode_number:
            raise ValidationError({
                "barcode_number": ["Barcode is required."]
            })

        search = (self.request.query_params.get("search") or "").strip()

        scanned_barcodes = (
            self.request.query_params.get("scanned_barcodes") or ""
        )

        scanned_barcodes_list = [
            barcode.strip()
            for barcode in scanned_barcodes.split(",")
            if barcode.strip()
        ]

        barcode_queryset = ProductVariant.objects.select_related(
            "product",
            "size",
            "color",
            "product__item_type",
            "product__company",
        ).filter(
            product__shop=self.request.user.shop,
            is_active=True,
            barcode_number=barcode_number,
        )

        total_count = barcode_queryset.count()

        self.request._is_multiple = total_count > 1

        if (
            total_count == 1
            and barcode_number in scanned_barcodes_list
        ):
            product = barcode_queryset.first()
            raise ValidationError({
                "quantity": [
                     f"{product.product.name} already scanned. Please increase quantity."
                ]
            })

        if search and total_count > 1:
            barcode_queryset = barcode_queryset.filter(
                Q(product__name__icontains=search)
                | Q(product__company__name__icontains=search)
                | Q(product__item_type__name__icontains=search)
            )

        return barcode_queryset.order_by("-created_at")
    

class CustomerLookupByPhoneViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CustomerLookupSerializer
    permission_classes = [IsEmployee]
    http_method_names = ["get"]

    def list(self, request, *args, **kwargs):
        phone = (kwargs.get("phone") or "").strip()
        if not phone:
            raise ValidationError({"phone": ["Phone number is required."]})

        customer = Customer.objects.filter(
            shop=request.user.shop,
            phone=phone,
            is_active=True,
        ).first()

        serialized_customer = self.get_serializer(customer).data
        return Response(serialized_customer)


class PaymentConfigQRListViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentConfigQRListSerializer
    permission_classes = [IsEmployee]
    http_method_names = ["get"]

    def get_queryset(self):
        return PaymentConfig.objects.filter(
            shop=self.request.user.shop,
            is_active=True,
            qr_image__isnull=False,
        ).order_by("-created_at")


class TodaySummaryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsEmployee]
    http_method_names = ["get"]
    queryset = Bill.objects.none()

    def list(self, request, *args, **kwargs):
        today = timezone.localdate()
        today_bills = Bill.objects.filter(
            created_by=request.user,
            shop=request.user.shop,
            created_at__date=today,
        )
        paid_today_bills = today_bills.filter(payment_status=Bill.PaymentStatus.PAID)

        total_sales_today = paid_today_bills.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        items_sold = BillItem.objects.filter(bill__in=paid_today_bills).aggregate(total=Sum("quantity"))["total"] or 0

        recent_activity = [
            {
                "bill_number": bill.bill_number,
                "payment_method": bill.payment_method,
                "amount": format_indian_amount(bill.total_amount),
            }
            for bill in today_bills.order_by("-created_at")[:10]
        ]

        return Response(
            {
                "today_summary": {
                    "total_sales_today": format_indian_amount(total_sales_today),
                    "bills_generated": today_bills.count(),
                    "items_sold": items_sold,
                },
                "recent_activity": recent_activity,
            },
            status=status.HTTP_200_OK,
        )


class SalesHistoryListViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SalesHistoryListSerializer
    permission_classes = [IsEmployee]
    pagination_class = SalesHistoryPagination
    http_method_names = ["get"]

    def get_queryset(self):
        params = self.request.query_params

        start_date_param = (params.get("start_date") or "").strip()
        end_date_param = (params.get("end_date") or "").strip()
        max_total_param = (params.get("max_total") or "").strip()
        search = (params.get("search") or "").strip()

        parsed_start_date = None
        parsed_end_date = None

        if start_date_param:
            try:
                parsed_start_date = datetime.strptime(start_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError({"start_date": ["Invalid date format. Use DD-MM-YYYY."]}) from exc

        if end_date_param:
            try:
                parsed_end_date = datetime.strptime(end_date_param, "%d-%m-%Y").date()
            except ValueError as exc:
                raise ValidationError({"end_date": ["Invalid date format. Use DD-MM-YYYY."]}) from exc

        if parsed_start_date and parsed_end_date and parsed_start_date > parsed_end_date:
            raise ValidationError({"date_range": ["start_date cannot be greater than end_date."]})

        queryset = Bill.objects.select_related("customer").filter(
            shop=self.request.user.shop,
            is_active=True,
        )

        if parsed_start_date:
            queryset = queryset.filter(created_at__date__gte=parsed_start_date)

        if parsed_end_date:
            queryset = queryset.filter(created_at__date__lte=parsed_end_date)

        if max_total_param:
            try:
                max_total = Decimal(max_total_param)
            except Exception as exc:
                raise ValidationError({"max_total": ["Invalid amount format."]}) from exc

            queryset = queryset.filter(total_amount__lte=max_total)

        if search:
            queryset = queryset.filter(customer__name__icontains=search)

        return queryset.order_by("-created_at")


class SalesHistoryDetailViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SalesHistoryDetailSerializer
    permission_classes = [IsEmployee]
    http_method_names = ["get"]

    def get_queryset(self):
        return Bill.objects.select_related(
            "customer",
        ).prefetch_related(
            "bill_items__product_variant__product__item_type",
        ).filter(
            shop=self.request.user.shop,
            is_active=True,
        )


class BillCreateViewSet(viewsets.ModelViewSet):
    serializer_class = BillCreateSerializer
    permission_classes = [IsEmployee]
    http_method_names = ["post"]
    queryset = ProductVariant.objects.none()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        customer, _ = Customer.objects.get_or_create(
            shop=request.user.shop,
            phone=validated_data["phone"],
            defaults={
                "name": validated_data.get("customer_name") or None,
                "address": validated_data.get("address") or None,
                "is_active": True,
            },
        )

        customer_name = validated_data.get("customer_name")
        customer_address = validated_data.get("address")

        if customer_name and customer.name != customer_name:
            customer.name = customer_name
        if customer_address and customer.address != customer_address:
            customer.address = customer_address
        if not customer.is_active:
            customer.is_active = True
        customer.save(update_fields=["name", "address", "is_active", "updated_at"])

        selected_payment_config = validated_data.get("selected_payment_config")

        bill = Bill(
            shop=request.user.shop,
            created_by=request.user,
            customer=customer,
            subtotal=validated_data["computed_subtotal"],
            discount_percent=validated_data.get("bill_discount_percent") or Decimal("0.00"),
            discount_amount=validated_data["computed_discount_amount"],
            total_amount=validated_data["computed_total_amount"],
            paid_amount=validated_data["computed_paid_amount"],
            payment_method=validated_data["payment_method"],
            payment_status=validated_data["payment_status"],
            selected_payment_config=selected_payment_config,
            payment_config_name=selected_payment_config.name if selected_payment_config else None,
            payment_config_value=(
                selected_payment_config.qr_image.name
                if selected_payment_config and selected_payment_config.qr_image
                else None
            ),
            notes=validated_data.get("notes") or "",
            is_active=True,
        )

        for _ in range(3):
            try:
                bill.bill_number = bill.generate_bill_number()
                bill.save()
                break
            except IntegrityError:
                continue
        else:
            raise ValidationError("Failed to generate unique bill number")

        prepared_items = validated_data["prepared_items"]

        variant_ids = [item["variant"].pk for item in prepared_items]

        variants_map = {
            v.id: v
            for v in ProductVariant.objects.select_for_update(of=("self",)).filter(id__in=variant_ids)
        }

        bill_items = []

        for item in prepared_items:
            variant = variants_map.get(item["variant"].pk)

            if not variant:
                raise ValidationError(f"Variant not found: {item['variant'].pk}")

            if variant.quantity < item["quantity"]:
                raise ValidationError(f"Insufficient stock for variant {variant.id}")

            variant.quantity -= item["quantity"]
            variant.save(update_fields=["quantity", "updated_at"])

            handle_stock_level_notification(variant)

            bill_items.append(
                BillItem(
                    bill=bill,
                    product_variant=variant,
                    quantity=item["quantity"],
                    price=item["price"],
                    discount_percent=item["discount_percent"],
                    discount_amount=item["discount_amount"],
                    total_price=item["total_price"],
                )
            )

        BillItem.objects.bulk_create(bill_items)

        try:
            created_items = bill.bill_items.all().order_by("created_at")
            pdf_path = generate_bill_pdf(
                bill=bill,
                items=created_items,
            )
            media_id = upload_pdf_to_meta(pdf_path, shop=request.user.shop)
            send_invoice_template_message(
                shop=request.user.shop,
                phone=bill.customer.phone,
                media_id=media_id,
                customer_name=bill.customer.name,
                bill_number=bill.bill_number,
            )
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

        except Exception as e:
            print(f"WhatsApp invoice send failed: {str(e)}")

        return Response(
            {
                "message": "Bill created successfully.",
                "bill_id": bill.id,
                "bill_number": bill.bill_number,
                "customer": {
                    "id": bill.customer.id if bill.customer else None,
                    "name": bill.customer.name if bill.customer else None,
                    "phone": bill.customer.phone if bill.customer else None,
                    "address": bill.customer.address if bill.customer else None,
                },
                "totals": {
                    "subtotal": str(bill.subtotal),
                    "discount_percent": str(bill.discount_percent),
                    "discount_amount": str(bill.discount_amount),
                    "total_amount": str(bill.total_amount),
                    "paid_amount": str(bill.paid_amount),
                },
                "payment": {
                    "method": bill.payment_method,
                    "status": bill.payment_status,
                    "selected_payment_config_id": (
                        str(bill.selected_payment_config.id)
                        if bill.selected_payment_config
                        else None
                    ),
                    "selected_payment_config_name": bill.payment_config_name,
                },
                "items": [
                    {
                        "id": item.id,
                        "product_variant_id": item.product_variant_id,
                        "quantity": item.quantity,
                        "price": str(item.price),
                        "discount_percent": str(item.discount_percent),
                        "discount_amount": str(item.discount_amount),
                        "total_price": str(item.total_price),
                    }
                    for item in bill.bill_items.all().order_by("created_at")
                ],
                "created_at": bill.created_at,
            },
            status=status.HTTP_201_CREATED,
        )

class NotificationUnreadListViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationUnreadSerializer
    permission_classes = [IsEmployee]
    http_method_names = ["get"]

    NOTIFICATION_AUTO_DELETE_AFTER = getattr(settings, 'NOTIFICATION_AUTO_DELETE_AFTER_HOURS', 48)

    def get_queryset(self):
        purge_expired_notifications(shop_id=self.request.user.shop_id)
        cutoff = timezone.now() - timedelta(hours=self.NOTIFICATION_AUTO_DELETE_AFTER)
        return (
            Notification.objects.filter(shop=self.request.user.shop)
            .filter(Q(is_seen=False) | Q(created_at__gte=cutoff))
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        unseen_total = Notification.objects.filter(
            shop=request.user.shop,
            is_seen=False,
        ).count()

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "total_unseen": unseen_total,
                "notifications": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class NotificationMarkSeenViewSet(viewsets.ModelViewSet):
    permission_classes = [IsEmployee]
    http_method_names = ["post"]
    queryset = Notification.objects.none()

    def create(self, request, *args, **kwargs):
        pending_queryset = Notification.objects.filter(
            shop=request.user.shop,
            is_seen=False,
        )

        updated = pending_queryset.update(is_seen=True)

        return Response(
            {
                "message": "Notifications marked as seen.",
                "updated_count": updated,
            },
            status=status.HTTP_200_OK,
        )


