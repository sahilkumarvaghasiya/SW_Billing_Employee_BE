from django import template

from apps.sales.utils import format_indian_amount

register = template.Library()


@register.filter
def indian_amount(value):
    return format_indian_amount(value)
