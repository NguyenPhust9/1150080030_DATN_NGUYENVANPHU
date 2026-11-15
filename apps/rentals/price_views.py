from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import PriceSuggestion, Room
from .permissions import get_accessible_rooms, is_admin, is_owner
from .pricing import suggest_room_price


def _manageable_room(user, room_id):
    if not (is_admin(user) or is_owner(user)):
        raise PermissionDenied("Chỉ chủ nhà hoặc quản trị viên được gợi ý và áp dụng giá.")
    return get_object_or_404(get_accessible_rooms(user).select_related("building").prefetch_related("amenities"), pk=room_id)


@login_required
def price_suggestion(request, room_id):
    room = _manageable_room(request.user, room_id)
    if request.method == "POST":
        try:
            suggested, count, mae, rmse, r2, snapshot = suggest_room_price(room)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            PriceSuggestion.objects.create(
                room=room, requested_by=request.user, current_price=room.monthly_rent,
                suggested_price=suggested, sample_count=count, validation_mae=mae,
                validation_rmse=rmse, validation_r2=r2, features=snapshot,
            )
            messages.success(request, "Đã lưu gợi ý giá mới. Giá thuê hiện tại chưa thay đổi cho đến khi bạn áp dụng.")
        return redirect("price-suggestion", room_id=room.id)

    suggestions = list(room.price_suggestions.select_related("requested_by")[:20])
    latest_suggestion = suggestions[0] if suggestions else None

    price_diff = None
    price_diff_percent = None
    price_diff_direction = None
    if latest_suggestion:
        price_diff = latest_suggestion.suggested_price - room.monthly_rent
        if room.monthly_rent and room.monthly_rent > 0:
            price_diff_percent = round((price_diff / room.monthly_rent) * 100, 1)
        if price_diff > 0:
            price_diff_direction = "up"
        elif price_diff < 0:
            price_diff_direction = "down"
        else:
            price_diff_direction = "equal"

    peer_qs = Room.objects.filter(
        building__owner_id=room.building.owner_id,
        area__gt=0,
        monthly_rent__gt=0,
    ).exclude(pk=room.pk)
    peer_count = peer_qs.count()

    return render(request, "rentals/price_suggestion.html", {
        "room": room,
        "suggestions": suggestions,
        "latest_suggestion": latest_suggestion,
        "price_diff": price_diff,
        "price_diff_abs": abs(price_diff) if price_diff is not None else None,
        "price_diff_percent": price_diff_percent,
        "price_diff_percent_abs": abs(price_diff_percent) if price_diff_percent is not None else None,
        "price_diff_direction": price_diff_direction,
        "peer_count": peer_count,
    })


@login_required
@require_POST
@transaction.atomic
def apply_price_suggestion(request, room_id, suggestion_id):
    room = _manageable_room(request.user, room_id)
    room = Room.objects.select_for_update().get(pk=room.pk)
    suggestion = get_object_or_404(
        PriceSuggestion.objects.select_for_update(), pk=suggestion_id, room=room
    )
    if suggestion.applied_at:
        messages.error(request, "Gợi ý này đã được áp dụng.")
    elif room.monthly_rent != suggestion.current_price:
        messages.error(request, "Giá phòng đã thay đổi. Hãy tạo gợi ý mới trước khi áp dụng.")
    else:
        room.monthly_rent = suggestion.suggested_price
        room.save(update_fields=("monthly_rent", "updated_at"))
        suggestion.applied_at = timezone.now()
        suggestion.save(update_fields=("applied_at", "updated_at"))
        messages.success(request, "Đã cập nhật giá niêm yết của phòng. Hợp đồng hiện tại không bị đổi giá.")
    return redirect("price-suggestion", room_id=room.id)
