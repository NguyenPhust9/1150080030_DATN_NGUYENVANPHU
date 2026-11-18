"""Read-only summaries of the complete, permission-scoped financial lists."""

from decimal import Decimal
from uuid import UUID

from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import ExtractYear
from django.utils import timezone

from .models import Invoice, Payment


ZERO = Decimal("0")


def building_filter_value(value):
    """Ignore malformed URLs before passing them to a UUID database field."""
    try:
        return str(UUID(value)) if value else ""
    except (ValueError, AttributeError, TypeError):
        return ""


def financial_period_filters(queryset, accessible_queryset, params, date_field):
    """Use invoice periods or local payment dates, preserving the base access scope."""
    selected = {}
    for part, upper in (("year", 9999), ("month", 12)):
        raw = params.get(part, "").strip()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        selected[part] = str(value) if 1 <= value <= upper else ""
        if selected[part]:
            # Avoid converting datetime range boundaries outside Python's valid
            # years when a timezone offset crosses the year 1 or 9999 boundary.
            lookup = Value(value) if part == "year" and value in {1, 9999} else value
            queryset = queryset.filter(**{f"{date_field}__{part}": lookup})
    years = list(
        accessible_queryset.order_by()
        .annotate(metric_year=ExtractYear(date_field))
        .values_list("metric_year", flat=True)
        .distinct()
        .order_by("-metric_year")
    )
    return queryset, {
        "selected_year": selected["year"],
        "selected_month": selected["month"],
        "year_choices": years,
        "month_choices": [(month, f"Tháng {month}") for month in range(1, 13)],
    }


def invoice_metrics(invoices):
    unpaid = Q(
        status__in=(Invoice.Status.ISSUED, Invoice.Status.PARTIAL, Invoice.Status.OVERDUE),
        total_amount__gt=F("paid_amount"),
    )
    overdue = unpaid & Q(due_date__lt=timezone.localdate())
    remaining = F("total_amount") - F("paid_amount")
    result = invoices.aggregate(
        total_count=Count("pk"),
        unpaid_count=Count("pk", filter=unpaid),
        unpaid_amount=Sum(remaining, filter=unpaid, default=ZERO),
        overdue_count=Count("pk", filter=overdue),
        overdue_amount=Sum(remaining, filter=overdue, default=ZERO),
        paid_count=Count("pk", filter=Q(status=Invoice.Status.PAID)),
    )
    # Aggregate payments separately: a join would duplicate invoices with more
    # than one receipt. The invoice subquery retains all filters and access rules.
    result["collected_amount"] = Payment.objects.filter(
        invoice_id__in=invoices.order_by().values("pk"), is_void=False
    ).aggregate(amount=Sum("amount", default=ZERO))["amount"]
    return result


def payment_metrics(payments):
    valid = Q(is_void=False)
    return payments.aggregate(
        total_count=Count("pk"),
        valid_count=Count("pk", filter=valid),
        void_count=Count("pk", filter=Q(is_void=True)),
        collected_amount=Sum("amount", filter=valid, default=ZERO),
        cash_amount=Sum("amount", filter=valid & Q(method=Payment.Method.CASH), default=ZERO),
        transfer_amount=Sum("amount", filter=valid & Q(method=Payment.Method.TRANSFER), default=ZERO),
        other_amount=Sum("amount", filter=valid & Q(method=Payment.Method.OTHER), default=ZERO),
    )
