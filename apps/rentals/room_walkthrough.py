"""Room walkthroughs reuse the same room visibility as the management portal."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import RoomMedia
from .permissions import get_accessible_rooms, is_tenant


@login_required
@require_GET
def room_walkthrough(request, room_id):
    room = get_object_or_404(
        get_accessible_rooms(request.user)
        .select_related("building")
        .prefetch_related("media"),
        pk=room_id,
        number="A101",
    )
    media = list(room.media.all())
    return_url = (
        reverse("tenant-rooms")
        if is_tenant(request.user)
        else reverse("room-update", args=[room.id])
    )
    return render(request, "rentals/room_walkthrough.html", {
        "room": room,
        "room_images": [item for item in media if item.media_type == RoomMedia.MediaType.IMAGE],
        "room_videos": [item for item in media if item.media_type == RoomMedia.MediaType.VIDEO],
        "return_url": return_url,
    })
