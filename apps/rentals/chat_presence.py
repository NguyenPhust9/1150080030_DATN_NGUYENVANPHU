from datetime import timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from .models import ChatPresence


def presence_for_users(user_ids):
    now = timezone.now()
    threshold = now - timedelta(seconds=65)
    rows = ChatPresence.objects.filter(user_id__in=user_ids).values("user_id").annotate(
        seen=Max("last_seen"),
        live=Count("connection", filter=Q(disconnected_at__isnull=True, last_seen__gte=threshold)),
    )
    result = {}
    for row in rows:
        online = bool(row["live"])
        seen = row["seen"]
        minutes = max(0, int((now - seen).total_seconds() // 60))
        if online:
            label = "Đang hoạt động"
        elif minutes < 1:
            label = "Vừa hoạt động"
        elif minutes < 60:
            label = f"Hoạt động {minutes} phút trước"
        elif minutes < 1440:
            label = f"Hoạt động {minutes // 60} giờ trước"
        else:
            label = "Hoạt động " + timezone.localtime(seen).strftime("%H:%M %d/%m")
        result[str(row["user_id"])] = {"online": online, "label": label, "last_seen": seen.isoformat()}
    return result


def offline_presence():
    return {"online": False, "label": "", "last_seen": None}
