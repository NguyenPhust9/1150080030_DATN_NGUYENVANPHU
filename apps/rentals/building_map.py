"""Read-only architectural map, matching the room tour's room/landing coordinates.

The tour is deliberately independent: do not change its builders to customize this
cutaway. Legacy map coordinates stay in the database for cameras and old clients.
"""
import heapq
import math
import re

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .models import Camera, HazardZone, IndoorMap, MapEdge, MapNode, MapZone, SafetyDevice
from .permissions import get_accessible_buildings, get_accessible_rooms, is_admin, is_owner


def natural_key(room):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", room.number)]


def floor_layouts(rooms):
    """Mirror buildRoomTourWorld's slots, including sparse A101–A105 slots."""
    floors = []
    for floor in sorted({room.floor for room in rooms}):
        candidates = sorted((room for room in rooms if room.floor == floor), key=natural_key)
        known = [int(room.number[-1]) - 1 for room in candidates if re.fullmatch(r"A10[1-5]", room.number)]
        next_slot = max(known) + 1 if known else 0
        items = []
        for room in candidates:
            detailed = bool(re.fullmatch(r"A10[1-5]", room.number))
            slot = int(room.number[-1]) - 1 if detailed else next_slot
            if not detailed:
                next_slot += 1
            x = round(-3.6 * slot, 2)
            half = 1.6 if room.number == "A101" else 1.7
            items.append({"id": f"room:{room.pk}", "room_id": str(room.pk), "number": room.number,
                          "label": f"Phòng {room.number}", "floor": floor, "kind": "room",
                          "status": room.get_status_display(), "profile": room.number if detailed else "generic",
                          "x": x, "z": -3.3, "min_x": round(x-half, 2), "max_x": round(x+half, 2),
                          "door_x": round(x+.55, 2), "hazard": False})
        lift_x = round(min(item["min_x"] for item in items) - .5 - 1.35 - .08, 2)
        floors.append({"number": floor, "rooms": items, "lift_x": lift_x,
                       "min_x": round(lift_x-1.47, 2), "max_x": round(max(r["max_x"] for r in items)+.6, 2),
                       "blocked": False})
    if floors:
        ground = min(1, floors[0]["number"])
        center = (min(r["x"] for f in floors for r in f["rooms"]) + max(r["x"] for f in floors for r in f["rooms"])) / 2
        for floor in floors:
            floor["elevation"] = (floor["number"] - ground) * 4.8
            floor["entrance_x"] = round(max(floor["lift_x"]+1.35+1.65, min(center, floor["max_x"]-1.65)), 2) if floor["number"] == ground else None
    return floors


def find_route(nodes, edges, start, end, mode, lift_disabled):
    by_id = {node["id"]: node for node in nodes}
    if not start:
        return [], "Chọn điểm bắt đầu và điểm đến để tìm đường."
    if start not in by_id or end not in by_id:
        return [], "Địa điểm không khả dụng trong bản đồ của bạn."
    adjacency = {key: [] for key in by_id}
    for edge in edges:
        a, b = by_id[edge["start"]], by_id[edge["end"]]
        if a["blocked"] or b["blocked"] or (edge["kind"] == "lift" and (mode == "evacuation" or lift_disabled)):
            continue
        distance = math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
        adjacency[a["id"]].append((b["id"], distance))
        adjacency[b["id"]].append((a["id"], distance))
    if by_id[start]["blocked"] or by_id[end]["blocked"]:
        return [], "Điểm bắt đầu hoặc điểm đến đang bị chặn."
    queue, distances, previous = [(0, start)], {start: 0}, {}
    while queue:
        distance, current = heapq.heappop(queue)
        if distance != distances[current]:
            continue
        if current == end:
            path = [current]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return [by_id[key] for key in reversed(path)], "Đã tìm thấy đường đi."
        for neighbour, weight in adjacency[current]:
            candidate = distance + weight
            if candidate < distances.get(neighbour, math.inf):
                distances[neighbour], previous[neighbour] = candidate, current
                heapq.heappush(queue, (candidate, neighbour))
    if mode == "evacuation" and by_id[start]["floor"] != by_id[end]["floor"]:
        return [], "Chưa có tuyến cầu thang thoát nạn được xác nhận cho tầng này. Không dùng thang máy để thoát nạn."
    return [], "Không có tuyến khả dụng. Hành lang bị chặn hoặc thang máy tạm ngừng khi có vùng cảnh báo."


def building_scene(building, user, params):
    rooms = list(get_accessible_rooms(user).filter(building=building))
    floors = floor_layouts(rooms)
    by_floor = {floor["number"]: floor for floor in floors}
    by_room = {room["room_id"]: room for floor in floors for room in floor["rooms"]}
    try:
        active_floor = int(params.get("floor", floors[0]["number"] if floors else 1))
    except (ValueError, TypeError):
        active_floor = floors[0]["number"] if floors else 1
    if active_floor not in by_floor and floors:
        active_floor = floors[0]["number"]
    maps = IndoorMap.objects.filter(building=building, floor__in=by_floor)
    hazards = list(HazardZone.objects.filter(indoor_map__in=maps, is_active=True).select_related("zone", "indoor_map"))
    hazard_ids = {hazard.zone_id for hazard in hazards}
    simulation_ids = {hazard.zone_id for hazard in hazards if hazard.is_simulation}
    warnings, zones, zone_locations = [], [], {}
    for blocked in MapNode.objects.filter(indoor_map__in=maps, is_blocked=True).select_related("indoor_map"):
        room = by_room.get(str(blocked.room_id))
        if room:
            room["hazard"] = True
        else:
            by_floor[blocked.indoor_map.floor]["blocked"] = True
            warnings.append(f"Tầng {blocked.indoor_map.floor}: có vị trí bị khóa trên mặt bằng cũ; cần kiểm tra lại lối đi.")
    for number in MapEdge.objects.filter(indoor_map__in=maps, is_blocked=True).values_list("indoor_map__floor", flat=True).distinct():
        by_floor[number]["blocked"] = True
        warnings.append(f"Tầng {number}: có lối đi bị khóa trên mặt bằng cũ; cần định vị lại trước khi chỉ đường.")
    for zone in MapZone.objects.filter(indoor_map__in=maps).select_related("indoor_map"):
        floor = by_floor[zone.indoor_map.floor]
        room = by_room.get(str(zone.room_id))
        # Room IDs are the only exact mapping from the old geometry. Corridors
        # map conservatively to the whole landing; old west/east exits do not.
        location = room if room else ({"x": (floor["min_x"]+floor["max_x"])/2, "z": 2.4} if zone.kind == "corridor" and not zone.room_id else None)
        if zone.id in hazard_ids:
            if room:
                room["hazard"] = True
            else:
                floor["blocked"] = True
                if not location:
                    warnings.append(f"Tầng {floor['number']}: có vùng cảnh báo của mặt bằng cũ chưa định vị lại; tạm khóa chỉ đường tại tầng này.")
        if zone.room_id and not room:
            continue
        if location:
            zone_locations[str(zone.id)] = {"x": location["x"], "z": location["z"], "floor": floor["number"]}
        zones.append({"id": str(zone.id), "name": zone.name, "floor": floor["number"], "mapped": bool(location),
                      "hazard": zone.id in hazard_ids, "simulation": zone.id in simulation_ids,
                      "url": reverse("indoor-map-toggle-hazard", args=[zone.indoor_map_id, zone.id])})
    cameras = []
    for camera in Camera.objects.filter(indoor_map__in=maps).select_related("indoor_map", "zone"):
        if camera.zone_id and camera.zone.room_id and str(camera.zone.room_id) not in by_room:
            continue
        cameras.append({"id": str(camera.id), "name": camera.name, "active": camera.is_active,
                        "floor": camera.indoor_map.floor, "location": zone_locations.get(str(camera.zone_id))})
    devices = [{"id": str(device.id), "name": device.name, "kind": device.kind, "floor": device.indoor_map.floor}
               for device in SafetyDevice.objects.filter(indoor_map__in=maps).select_related("indoor_map")]
    nodes, edges, places = [], [], []

    def node(key, label, kind, floor, x, z, blocked=False):
        item = {"id": key, "label": label, "kind": kind, "floor": floor["number"], "x": x, "y": floor["elevation"], "z": z,
                "blocked": blocked or floor["blocked"]}
        nodes.append(item)
        if kind in ("room", "lift", "entrance"):
            places.append(item)
        return key

    def edge(a, b, kind="walk"):
        edges.append({"start": a, "end": b, "kind": kind})

    entrance_id = ""
    for floor in floors:
        number = floor["number"]
        lift = node(f"lift:{number}", "Thang máy", "lift", floor, floor["lift_x"], 2.4)
        hall = [(floor["lift_x"], lift)]
        for room in floor["rooms"]:
            key = room["id"]
            node(key, room["label"], "room", floor, room["door_x"], -1.4, room["hazard"])
            door = node(f"door:{room['room_id']}", f"Cửa {room['number']}", "door", floor, room["door_x"], 0, room["hazard"])
            landing = node(f"hall:{room['room_id']}", "Hành lang", "hall", floor, room["door_x"], 2.4)
            edge(key, door)
            edge(door, landing)
            hall.append((room["door_x"], landing))
        if floor["entrance_x"] is not None:
            x = floor["entrance_x"]
            entrance_id = node(f"entrance:{number}", "Lối vào tòa nhà", "entrance", floor, x, 5.8)
            front = node(f"front:{number}", "Cửa chính", "door", floor, x, 3.7)
            landing = node(f"entry-hall:{number}", "Sảnh vào", "hall", floor, x, 2.4)
            edge(entrance_id, front)
            edge(front, landing)
            hall.append((x, landing))
        hall.sort()
        for (_, a), (_, b) in zip(hall, hall[1:]):
            edge(a, b)
    for a, b in zip(floors, floors[1:]):
        edge(f"lift:{a['number']}", f"lift:{b['number']}", "lift")
    start = params.get("start", "")
    mode = "evacuation" if params.get("mode") == "evacuation" else "visit"
    end = entrance_id if mode == "evacuation" else params.get("end", "") or entrance_id
    points, reason = find_route(nodes, edges, start, end, mode, bool(hazards))
    transfers = [{"from": a["floor"], "to": b["floor"]} for a, b in zip(points, points[1:]) if a["floor"] != b["floor"]]
    return {"schema_version": 2, "building": {"id": str(building.pk), "name": building.name}, "floor": active_floor,
            "floors": floors, "places": places, "nodes": nodes, "edges": edges, "zones": zones, "cameras": cameras, "devices": devices,
            "warnings": list(dict.fromkeys(warnings)), "can_simulate": is_admin(user) or is_owner(user),
            "url": reverse("building-indoor-map", args=[building.pk]),
            "route": {"start_id": start, "end_id": end, "mode": mode, "found": bool(points), "points": points,
                      "transfers": transfers, "reason": reason, "destination": points[-1]["label"] if points else ""}}


@login_required
def building_indoor_map(request, building_id):
    building = get_object_or_404(get_accessible_buildings(request.user), pk=building_id)
    scene = building_scene(building, request.user, request.GET)
    if request.GET.get("format") == "json":
        return JsonResponse(scene)
    return render(request, "rentals/indoor_map.html", {"scene_data": scene, "building": building})
