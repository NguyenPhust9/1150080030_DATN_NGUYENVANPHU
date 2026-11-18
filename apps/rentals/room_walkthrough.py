"""Room walkthroughs reuse the same room visibility as the management portal."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import RoomMedia
from .permissions import get_accessible_rooms, is_tenant


SUPPORTED_ROOMS = ("A101", "A102", "A103", "A104", "A105")


@login_required
@require_GET
def room_walkthrough(request, room_id):
    accessible_rooms = get_accessible_rooms(request.user)
    room = get_object_or_404(
        accessible_rooms.select_related("building"),
        pk=room_id,
        number__in=SUPPORTED_ROOMS,
    )
    # The shared corridor must not reveal a neighbour's room or media to a
    # tenant who only has permission to enter their own room.
    tour_rooms = []
    for tour_room in accessible_rooms.filter(
        building_id=room.building_id, number__in=SUPPORTED_ROOMS,
    ).prefetch_related("media").order_by("number"):
        media = list(tour_room.media.all())
        tour_rooms.append({
            "number": tour_room.number,
            "images": [item for item in media if item.media_type == RoomMedia.MediaType.IMAGE],
            "videos": [item for item in media if item.media_type == RoomMedia.MediaType.VIDEO],
        })
    entry_room = next(item for item in tour_rooms if item["number"] == room.number)
    return_url = (
        reverse("tenant-rooms")
        if is_tenant(request.user)
        else reverse("room-update", args=[room.id])
    )
    return render(request, "rentals/room_walkthrough.html", {
        "room": room,
        "room_images": entry_room["images"],
        "room_videos": entry_room["videos"],
        "tour_rooms": tour_rooms,
        "tour_config": {
            "entryRoom": room.number,
            "rooms": [item["number"] for item in tour_rooms],
        },
        "return_url": return_url,
    })
