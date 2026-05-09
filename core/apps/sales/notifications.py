from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.sales.models import Notification


NOTIFICATION_AUTO_DELETE_AFTER = getattr(
    settings, 'NOTIFICATION_AUTO_DELETE_AFTER_HOURS', 48
)
@transaction.atomic
def purge_expired_notifications(shop_id=None):
    cutoff = timezone.now() - timedelta(hours=NOTIFICATION_AUTO_DELETE_AFTER)
    queryset = Notification.objects.filter(is_seen=True, created_at__lt=cutoff)

    if shop_id is not None:
        queryset = queryset.filter(shop_id=shop_id)

    deleted_count, _ = queryset.delete()
    return deleted_count


def _variant_descriptor(variant):
    product_name = None
    if variant.product and variant.product.item_type:
        product_name = variant.product.item_type.name
    elif variant.product:
        product_name = variant.product.name

    size = variant.size.name if variant.size else None
    color = variant.color.name if variant.color else None

    details = []
    if size:
        details.append(f"Size: {size}")
    if color:
        details.append(f"Color: {color}")

    detail_text = f" ({', '.join(details)})" if details else ""
    return f"{product_name or 'Product'}{detail_text}"


def _should_suppress_stock_alert(alert_already_sent):
    if not alert_already_sent:
        return False
    return True


def handle_stock_level_notification(variant):
    """Create/update stock notifications based on latest quantity.

    Rules:
    - quantity == 0 => OUT_OF_STOCK
    - quantity <= threshold => LOW_STOCK
    - quantity > threshold => resolve old stock alerts by marking as read
    """
    variant_model = type(variant)

    if not hasattr(variant, "product"):
        variant = variant_model.objects.select_related("product", "size", "color").get(pk=variant.pk)

    purge_expired_notifications(shop_id=variant.product.shop_id)

    Notification.objects.filter(
        shop=variant.product.shop,
        product_variant=variant,
        type__in=[Notification.Type.LOW_STOCK, Notification.Type.OUT_OF_STOCK, Notification.Type.PRE_LOW_STOCK],
        is_seen=False,
    ).exclude(
        type=(
            Notification.Type.OUT_OF_STOCK
            if variant.quantity == 0
            else Notification.Type.LOW_STOCK
        )
    ).update(is_seen=True)

    pre_alert_buffer = getattr(
        settings,"LOW_STOCK_PRE_ALERT_BUFFER",10)

    pre_alert_quantity = (
        variant.low_stock_threshold + pre_alert_buffer
    )

    if (
        variant.quantity <= pre_alert_quantity
        and variant.quantity > variant.low_stock_threshold
    ):

        existing_pre_alert = Notification.objects.filter(
            shop=variant.product.shop,
            type=Notification.Type.PRE_LOW_STOCK,
            product_variant=variant,
            is_seen=False,
        ).first()

        if existing_pre_alert:
            return existing_pre_alert

        if variant.pre_low_stock_alert_sent_once:
            return None

        descriptor = _variant_descriptor(variant)

        notification = Notification.objects.create(
            shop=variant.product.shop,
            type=Notification.Type.PRE_LOW_STOCK,
            title="Stock reaching low level",
            message=(
                f"{descriptor} stock is reaching low level "
                f"({variant.quantity} left). "
                f"Low stock threshold is "
                f"{variant.low_stock_threshold}."
            ),
            priority=Notification.Priority.LOW,
            product_variant=variant,
        )

        variant.pre_low_stock_alert_sent_once = True

        variant.save(
            update_fields=[
                "pre_low_stock_alert_sent_once",
                "updated_at",
            ]
        )

        return notification

    if variant.quantity > variant.low_stock_threshold:
        Notification.objects.filter(
            shop=variant.product.shop,
            product_variant=variant,
            type__in=[Notification.Type.LOW_STOCK, Notification.Type.OUT_OF_STOCK, Notification.Type.PRE_LOW_STOCK],
            is_seen=False,
        ).update(is_seen=True)

        variant.low_stock_alert_sent_once = False
        variant.out_of_stock_alert_sent_once = False
        variant.pre_low_stock_alert_sent_once = False
        variant.save(
            update_fields=[
                "low_stock_alert_sent_once",
                "out_of_stock_alert_sent_once",
                "pre_low_stock_alert_sent_once",
                "updated_at",
            ]
        )
        return None

    descriptor = _variant_descriptor(variant)

    if variant.quantity == 0:
        notification_type = Notification.Type.OUT_OF_STOCK
        title = "Out of stock"
        message = f"{descriptor} is out of stock."
        priority = Notification.Priority.HIGH
        alert_already_sent = variant.out_of_stock_alert_sent_once
    else:
        notification_type = Notification.Type.LOW_STOCK
        title = "Low stock"
        message = f"{descriptor} is low in stock ({variant.quantity} left)."
        priority = Notification.Priority.MEDIUM
        alert_already_sent = variant.low_stock_alert_sent_once

    unseen_existing = Notification.objects.filter(
        shop=variant.product.shop,
        type=notification_type,
        product_variant=variant,
        is_seen=False,
    ).first()

    if unseen_existing:
        return unseen_existing

    if _should_suppress_stock_alert(
        alert_already_sent=alert_already_sent,
    ):
        return None

    notification = Notification.objects.create(
        shop=variant.product.shop,
        type=notification_type,
        title=title,
        message=message,
        priority=priority,
        product_variant=variant,
    )

    if notification_type == Notification.Type.OUT_OF_STOCK:
        variant.out_of_stock_alert_sent_once = True
        variant.save(
            update_fields=[
                "out_of_stock_alert_sent_once",
                "updated_at",
            ]
        )
    else:
        variant.low_stock_alert_sent_once = True
        variant.save(
            update_fields=[
                "low_stock_alert_sent_once",
                "updated_at",
            ]
        )

    return notification


def create_vendor_payment_due_notification(stock_entry):
    purge_expired_notifications(shop_id=stock_entry.shop_id)

    if stock_entry.is_fully_paid:
        mark_vendor_payment_due_notification_resolved(stock_entry)
        return

    today = timezone.localdate()

    existing_notification = Notification.objects.filter(
        shop_id=stock_entry.shop_id,
        type=Notification.Type.VENDOR_PAYMENT_DUE,
        stock_entry=stock_entry,
        is_seen=False,
        created_at__date=today,
    ).first()

    if existing_notification:
        return

    Notification.objects.filter(
        shop_id=stock_entry.shop_id,
        type=Notification.Type.VENDOR_PAYMENT_DUE,
        stock_entry=stock_entry,
        is_seen=False,
    ).update(is_seen=True)

    due_text = (
        stock_entry.due_date.strftime("%d %b %Y")
        if stock_entry.due_date
        else "N/A"
    )
    due_amount = stock_entry.total_amount - stock_entry.paid_amount
    Notification.objects.create(
        shop_id=stock_entry.shop_id,
        type=Notification.Type.VENDOR_PAYMENT_DUE,
        title="Vendor payment deadline",
        message=(
            f"Payment due for {stock_entry.vendor.name} "
            f"on {due_text}. Total: {stock_entry.total_amount}, "
            f"Paid: {stock_entry.paid_amount}, Due: {due_amount}."
        ),
        priority=Notification.Priority.HIGH,
        stock_entry=stock_entry,
    )

@transaction.atomic
def mark_vendor_payment_due_notification_resolved(stock_entry):
    return Notification.objects.filter(
        shop_id=stock_entry.shop_id,
        type=Notification.Type.VENDOR_PAYMENT_DUE,
        stock_entry=stock_entry,
        is_seen=False,
    ).update(is_seen=True)
