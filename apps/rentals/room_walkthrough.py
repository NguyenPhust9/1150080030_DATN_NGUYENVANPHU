"""Room walkthroughs reuse the same room visibility as the management portal."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import RoomMedia
from .permissions import get_accessible_rooms, is_tenant


# These rooms have interiors built from reference photos and videos. Other
# existing rooms use a simple layout until their own reference model is ready.
DETAILED_ROOM_PROFILES = frozenset(("A101", "A102", "A103", "A104", "A105"))


@login_required
@require_GET
def room_walkthrough(request, room_id):
    accessible_rooms = get_accessible_rooms(request.user)
    room = get_object_or_404(
        accessible_rooms.select_related("building"),
        pk=room_id,
    )
    # The shared corridor must not reveal a neighbour's room or media to a
    # tenant who only has permission to enter their own room.
    tour_rooms = []
    room_details = []
    for tour_room in accessible_rooms.filter(
        building_id=room.building_id,
    ).prefetch_related("media").order_by("floor", "number"):
        media = list(tour_room.media.all())
        tour_rooms.append({
            "number": tour_room.number,
            "images": [item for item in media if item.media_type == RoomMedia.MediaType.IMAGE],
            "videos": [item for item in media if item.media_type == RoomMedia.MediaType.VIDEO],
        })
        room_details.append({
            "number": tour_room.number,
            "floor": tour_room.floor,
            "status": tour_room.status,
            "statusLabel": tour_room.get_status_display(),
            "area": float(tour_room.area) if tour_room.area is not None else None,
            "profile": tour_room.number if tour_room.number in DETAILED_ROOM_PROFILES else "generic",
            "hasMedia": bool(media),
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
            "entryFloor": room.floor,
            "buildingName": room.building.name,
            "rooms": [item["number"] for item in tour_rooms],
            "roomDetails": room_details,
            "floors": sorted({item["floor"] for item in room_details}),
        },
        "return_url": return_url,
    })
