from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def vnd(value):
    """Format a number with Vietnamese thousands separators, without a currency suffix."""
    if value in (None, ""):
        return "0"
    try:
        amount = Decimal(str(value)).quantize(Decimal("1"))
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{amount:,.0f}".replace(",", ".")
