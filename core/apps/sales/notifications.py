from django.db import transaction

from apps.sales.models import Notification


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


@transaction.atomic
def handle_stock_level_notification(variant):
    """Create/update stock notifications based on latest quantity.

    Rules:
    - quantity == 0 => OUT_OF_STOCK
    - quantity <= threshold => LOW_STOCK
    - quantity > threshold => resolve old stock alerts by marking as read
    """
    Notification.objects.filter(
        shop=variant.product.shop,
        product_variant=variant,
        type__in=[Notification.Type.LOW_STOCK, Notification.Type.OUT_OF_STOCK],
        is_read=False,
    ).exclude(
        type=(
            Notification.Type.OUT_OF_STOCK
            if variant.quantity == 0
            else Notification.Type.LOW_STOCK
        )
    ).update(is_read=True)

    if variant.quantity > variant.low_stock_threshold:
        Notification.objects.filter(
            shop=variant.product.shop,
            product_variant=variant,
            type__in=[Notification.Type.LOW_STOCK, Notification.Type.OUT_OF_STOCK],
            is_read=False,
        ).update(is_read=True)
        return None

    descriptor = _variant_descriptor(variant)

    if variant.quantity == 0:
        notification_type = Notification.Type.OUT_OF_STOCK
        title = "Out of stock"
        message = f"{descriptor} is out of stock."
        priority = Notification.Priority.HIGH
    else:
        notification_type = Notification.Type.LOW_STOCK
        title = "Low stock"
        message = f"{descriptor} is low in stock ({variant.quantity} left)."
        priority = Notification.Priority.MEDIUM

    unread_existing = Notification.objects.filter(
        shop=variant.product.shop,
        type=notification_type,
        product_variant=variant,
        is_read=False,
    ).first()

    if unread_existing:
        return unread_existing

    return Notification.objects.create(
        shop=variant.product.shop,
        type=notification_type,
        title=title,
        message=message,
        priority=priority,
        product_variant=variant,
    )


@transaction.atomic
def create_vendor_payment_due_notification(stock_entry):
    if stock_entry.is_fully_paid:
        mark_vendor_payment_due_notification_resolved(stock_entry)
        return None, False

    unread_existing = Notification.objects.filter(
        shop_id=stock_entry.shop_id,
        type=Notification.Type.VENDOR_PAYMENT_DUE,
        stock_entry=stock_entry,
        is_read=False,
    ).first()

    if unread_existing:
        return unread_existing, False

    due_text = stock_entry.due_date.strftime("%d %b %Y") if stock_entry.due_date else "N/A"
    due_amount = stock_entry.total_amount - stock_entry.paid_amount
    return Notification.objects.create(
        shop_id=stock_entry.shop_id,
        type=Notification.Type.VENDOR_PAYMENT_DUE,
        title="Vendor payment deadline",
        message=(
            f"Payment due for {stock_entry.vendor.name} "
            f"on {due_text}. Total: {stock_entry.total_amount}, Paid: {stock_entry.paid_amount}, Due: {due_amount}."
        ),
        priority=Notification.Priority.HIGH,
        stock_entry=stock_entry,
    ), True


@transaction.atomic
def mark_vendor_payment_due_notification_resolved(stock_entry):
    return Notification.objects.filter(
        shop_id=stock_entry.shop_id,
        type=Notification.Type.VENDOR_PAYMENT_DUE,
        stock_entry=stock_entry,
        is_read=False,
    ).update(is_read=True)
