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


@register.simple_tag(takes_context=True)
def unread_notifications_count(context):
    request = context.get("request")
    user = getattr(request, "user", None) or context.get("user")
    if user and getattr(user, "is_authenticated", False):
        return user.notifications.filter(is_read=False).count()
    return 0


@register.simple_tag(takes_context=True)
def unread_chat_count(context):
    request = context.get("request")
    user = getattr(request, "user", None) or context.get("user")
    if not user or not getattr(user, "is_authenticated", False):
        return 0

    from apps.rentals.models import ChatMessage
    from apps.rentals.permissions import get_accessible_conversations

    return (
        ChatMessage.objects.filter(
            conversation__in=get_accessible_conversations(user)
        )
        .exclude(sender=user)
        .exclude(read_by=user)
        .distinct()
        .count()
    )


@register.filter(name="has_perm_code")
def has_perm_code_filter(user, perm_code: str) -> bool:
    from apps.rentals.permissions import has_perm_code

    return has_perm_code(user, perm_code)

