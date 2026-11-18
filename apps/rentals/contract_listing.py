"""Read-only contract list summaries and date-aware card presentation."""

from datetime import timedelta

from django.db.models import Count, Q

from .models import Contract


EXPIRING_DAYS = 30
CONTRACT_STATUS_CHOICES = (
    (Contract.Status.ACTIVE, "Hoạt động"),
    ("expiring", "Sắp hết hạn"),
    (Contract.Status.EXPIRED, "Đã hết hạn"),
    ("upcoming", "Chưa đến ngày bắt đầu"),
    (Contract.Status.DRAFT, "Bản nháp"),
    (Contract.Status.TERMINATED, "Đã chấm dứt"),
    (Contract.Status.CANCELLED, "Đã hủy"),
)
STATUS_LABELS = dict(CONTRACT_STATUS_CHOICES)


def contract_status_filters(today):
    """Classify dates without changing the stored lifecycle status."""
    active = Q(
        status=Contract.Status.ACTIVE, start_date__lte=today, end_date__gte=today
    )
    return {
        Contract.Status.ACTIVE: active,
        "expiring": active & Q(end_date__lte=today + timedelta(days=EXPIRING_DAYS)),
        Contract.Status.EXPIRED: Q(status=Contract.Status.EXPIRED)
        | Q(status=Contract.Status.ACTIVE, end_date__lt=today),
        "upcoming": Q(status=Contract.Status.ACTIVE, start_date__gt=today),
        Contract.Status.DRAFT: Q(status=Contract.Status.DRAFT),
        Contract.Status.TERMINATED: Q(status=Contract.Status.TERMINATED),
        Contract.Status.CANCELLED: Q(status=Contract.Status.CANCELLED),
    }


def contract_metrics(contracts, today):
    """Summarize all filtered, permission-scoped results before pagination."""
    filters = contract_status_filters(today)
    return contracts.aggregate(
        total_count=Count("pk"),
        active_count=Count("pk", filter=filters[Contract.Status.ACTIVE]),
        expiring_count=Count("pk", filter=filters["expiring"]),
        expired_count=Count("pk", filter=filters[Contract.Status.EXPIRED]),
    )


def contract_presentation(contract, today):
    """Return display data only; an elapsed contract remains unchanged in storage."""
    total_days = max(0, (contract.end_date - contract.start_date).days)
    elapsed_days = min(total_days, max(0, (today - contract.start_date).days))
    status_key = contract.status
    if status_key == Contract.Status.ACTIVE:
        if contract.end_date < today:
            status_key = Contract.Status.EXPIRED
        elif contract.start_date > today:
            status_key = "upcoming"
        elif contract.end_date <= today + timedelta(days=EXPIRING_DAYS):
            status_key = "expiring"

    remaining_days = 0
    remaining_percent = 0
    tone = "blue"
    time_label = STATUS_LABELS.get(status_key, contract.get_status_display())
    time_detail = f"Thời hạn {total_days} ngày"

    if status_key in {Contract.Status.ACTIVE, "expiring"}:
        remaining_days = min(total_days, max(0, (contract.end_date - today).days))
        remaining_percent = round(remaining_days * 100 / total_days) if total_days else 0
        tone = "amber" if status_key == "expiring" else "green"
        time_label = "Còn lại"
        time_detail = f"{remaining_days} / {total_days} ngày"
    elif status_key == "upcoming":
        remaining_days = total_days
        remaining_percent = 100 if total_days else 0
        time_label = "Bắt đầu sau"
        time_detail = f"{(contract.start_date - today).days} ngày"
    elif status_key == Contract.Status.EXPIRED:
        tone = "red"
        days_overdue = (today - contract.end_date).days
        time_detail = (
            f"Đã kết thúc {days_overdue} ngày" if days_overdue > 0 else "Hợp đồng đã hết hạn"
        )
    elif status_key == Contract.Status.DRAFT:
        time_label = "Chưa kích hoạt"
    elif status_key == Contract.Status.CANCELLED:
        tone = "red"

    return {
        "status_key": status_key,
        "status_label": STATUS_LABELS.get(status_key, contract.get_status_display()),
        "tone": tone,
        "remaining_days": remaining_days,
        "total_days": total_days,
        "elapsed_days": elapsed_days,
        "remaining_percent": max(0, min(100, remaining_percent)),
        "show_progress": status_key in {Contract.Status.ACTIVE, "expiring"},
        "time_label": time_label,
        "time_detail": time_detail,
    }
