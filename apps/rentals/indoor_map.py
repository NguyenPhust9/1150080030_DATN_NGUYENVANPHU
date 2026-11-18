import heapq
import math
import uuid
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import HazardZone, IndoorMap, MapNode, MapZone
from .permissions import get_accessible_buildings, is_admin, is_owner


def point_in_zone(x, y, zone):
    return zone.x <= x <= zone.x + zone.width and zone.y <= y <= zone.y + zone.height


def segment_intersects_zone(a, b, zone):
    """Liang-Barsky clipping: detect whether a walk segment enters a blocked rectangle."""
    dx, dy = b.x - a.x, b.y - a.y
    low, high = 0.0, 1.0
    for p, q in (
        (-dx, a.x - zone.x),
        (dx, zone.x + zone.width - a.x),
        (-dy, a.y - zone.y),
        (dy, zone.y + zone.height - a.y),
    ):
        if p == 0:
            if q < 0:
                return False
            continue
        ratio = q / p
        if p < 0:
            low = max(low, ratio)
        else:
            high = min(high, ratio)
        if low > high:
            return False
    return True


def shortest_exit(nodes, edges, start_id, blocked_zones=(), end_id=None):
    blocked_zones = list(blocked_zones)
    by_id = {str(node.id): node for node in nodes}
    start_id = str(start_id)
    end_id = str(end_id) if end_id else None
    if end_id and end_id not in by_id:
        return []
    if start_id not in by_id or by_id[start_id].is_blocked or any(
        point_in_zone(by_id[start_id].x, by_id[start_id].y, zone) for zone in blocked_zones
    ):
        return []
    graph = {
        node_id: [] for node_id, node in by_id.items()
        if not node.is_blocked and not any(point_in_zone(node.x, node.y, zone) for zone in blocked_zones)
    }
    for edge in edges:
        a, b = str(edge.start_id), str(edge.end_id)
        if edge.is_blocked or a not in graph or b not in graph:
            continue
        if any(segment_intersects_zone(by_id[a], by_id[b], zone) for zone in blocked_zones):
            continue
        weight = math.hypot(by_id[a].x - by_id[b].x, by_id[a].y - by_id[b].y)
        graph[a].append((b, weight))
        graph[b].append((a, weight))
    queue = [(0, start_id)]
    distance = {start_id: 0}
    previous = {}
    while queue:
        cost, current = heapq.heappop(queue)
        if cost > distance[current]:
            continue
        reached_goal = current == end_id if end_id else by_id[current].kind == MapNode.Kind.EXIT
        if reached_goal:
            path = [current]
            while current in previous:
                current = previous[current]
                path.append(current)
            return list(reversed(path))
        for neighbour, weight in graph[current]:
            candidate = cost + weight
            if candidate < distance.get(neighbour, float("inf")):
                distance[neighbour] = candidate
                previous[neighbour] = current
                heapq.heappush(queue, (candidate, neighbour))
    return []


def scene_for_map(indoor, start_id="", end_id=""):
    """One geometry/route source for the HTML, WebGL and JSON representations."""
    nodes = list(indoor.nodes.select_related("room"))
    edges = list(indoor.edges.select_related("start", "end"))
    zones = list(indoor.zones.select_related("room").order_by("kind", "name"))
    hazards = list(indoor.hazards.filter(is_active=True).select_related("zone", "camera"))
    blocked = [hazard.zone for hazard in hazards]
    by_id = {str(node.id): node for node in nodes}
    path = shortest_exit(nodes, edges, start_id, blocked, end_id) if start_id else []
    is_demo = "minh họa" in indoor.name.lower() or "mặt bằng mẫu" in indoor.name.lower()
    # Only our explicitly generated layout has an assumed scale. Never invent
    # measurements for an arbitrary imported or surveyed map.
    scale = 0.04 if indoor.name.startswith("Mặt bằng mẫu 3D") else None
    zone_data = []
    for zone in zones:
        room_nodes = [node for node in nodes if zone.room_id and node.room_id == zone.room_id]
        door = None
        if room_nodes:
            room_node = room_nodes[0]
            neighbours = [by_id.get(str(edge.end_id if edge.start_id == room_node.id else edge.start_id))
                          for edge in edges if room_node.id in (edge.start_id, edge.end_id)]
            for node in neighbours:
                if node and zone.x <= node.x <= zone.x + zone.width:
                    if node.y in (zone.y, zone.y + zone.height):
                        door = {"x": node.x, "y": node.y, "width": 38,
                                "side": "north" if node.y == zone.y else "south"}
                        break
        zone_data.append({
            "id": str(zone.id), "name": zone.name, "kind": zone.kind,
            "x": zone.x, "y": zone.y, "width": zone.width, "height": zone.height,
            "hazard": any(h.zone_id == zone.id for h in hazards),
            "simulation": any(h.zone_id == zone.id and h.is_simulation for h in hazards),
            "room_id": str(zone.room_id) if zone.room_id else None,
            "room_number": zone.room.number if zone.room_id else None,
            "status": zone.room.get_status_display() if zone.room_id else "",
            "node_id": str(room_nodes[0].id) if room_nodes else None, "door": door,
        })
    distance = sum(math.hypot(by_id[a].x - by_id[b].x, by_id[a].y - by_id[b].y)
                   for a, b in zip(path, path[1:]))
    return {
        "map": {"id": str(indoor.id), "name": indoor.name, "building": indoor.building.name,
                "floor": indoor.floor, "width": indoor.width, "height": indoor.height,
                "is_demo": is_demo, "meters_per_unit": scale},
        "zones": zone_data,
        "nodes": [{"id": str(n.id), "label": n.label, "kind": n.kind, "x": n.x, "y": n.y,
                   "blocked": n.is_blocked or any(point_in_zone(n.x, n.y, z) for z in blocked)} for n in nodes],
        "edges": [{"start": str(e.start_id), "end": str(e.end_id),
                   "blocked": e.is_blocked or e.start.is_blocked or e.end.is_blocked
                   or any(segment_intersects_zone(e.start, e.end, z) for z in blocked)} for e in edges],
        "devices": [{"id": str(d.id), "name": d.name, "kind": d.kind, "x": d.x, "y": d.y}
                    for d in indoor.safety_devices.all()],
        "cameras": [{"id": str(c.id), "name": c.name, "zone_id": str(c.zone_id), "active": c.is_active,
                     "x": c.zone.x + c.zone.width / 2, "y": c.zone.y + 16}
                    for c in indoor.cameras.select_related("zone") if c.zone_id],
        "route": {"start_id": start_id, "end_id": end_id, "found": bool(path),
                  "points": [{"x": by_id[p].x, "y": by_id[p].y, "id": p, "label": by_id[p].label} for p in path],
                  "distance_m": round(distance * scale, 1) if path and scale else None,
                  "exit_label": by_id[path[-1]].label if path else "",
                  "reason": "Chưa chọn điểm bắt đầu." if not start_id else (
                      "Đã tìm thấy tuyến đường." if path else "Không có đường đi khả dụng. Vị trí hoặc lối đi đang bị chặn.")},
    }


@login_required
def indoor_map_list(request):
    from .permissions import get_accessible_rooms
    buildings = list(get_accessible_buildings(request.user).order_by("name"))
    rooms = list(get_accessible_rooms(request.user).values("building_id", "floor"))
    for building in buildings:
        visible = [room for room in rooms if room["building_id"] == building.id]
        building.map_floor_count = len({room["floor"] for room in visible})
        building.map_room_count = len(visible)
    return render(request, "rentals/indoor_map_list.html", {"buildings": buildings})


@login_required
def indoor_map(request, map_id):
    indoor = get_object_or_404(
        IndoorMap.objects.select_related("building").filter(building__in=get_accessible_buildings(request.user)),
        pk=map_id,
    )
    # Legacy JSON clients retain saved coordinates; HTML uses the new geometry.
    if request.GET.get("format") == "json":
        return JsonResponse(scene_for_map(indoor, request.GET.get("start", ""), request.GET.get("end", "")))
    from .building_map import building_scene
    params = request.GET.copy()
    params.setdefault("floor", str(indoor.floor))
    for key in ("start", "end"):
        try:
            legacy = indoor.nodes.filter(pk=uuid.UUID(params.get(key, ""))).first()
        except (ValueError, AttributeError):
            legacy = None
        if legacy and legacy.room_id:
            params[key] = f"room:{legacy.room_id}"
        elif legacy:
            params[key] = ""
    scene = building_scene(indoor.building, request.user, params)
    return render(request, "rentals/indoor_map.html", {"scene_data": scene, "building": indoor.building})


@login_required
@require_POST
@transaction.atomic
def toggle_hazard_simulation(request, map_id, zone_id):
    if not (is_admin(request.user) or is_owner(request.user)):
        raise PermissionDenied
    indoor = get_object_or_404(
        IndoorMap.objects.select_for_update().filter(building__in=get_accessible_buildings(request.user)), pk=map_id
    )
    zone = get_object_or_404(MapZone, pk=zone_id, indoor_map=indoor)
    simulations = HazardZone.objects.filter(
        indoor_map=indoor, zone=zone, is_simulation=True, is_active=True
    )
    if simulations.exists():
        simulations.update(is_active=False)
    else:
        HazardZone.objects.create(
            indoor_map=indoor, zone=zone, is_simulation=True,
            note="Mô phỏng thủ công trên bản đồ; không phải cảnh báo cháy thực tế.",
        )
    target = redirect("indoor-map", map_id=indoor.id)
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse(scene_for_map(indoor, request.POST.get("start", ""), request.POST.get("end", "")))
    start_id = request.POST.get("start", "")
    if start_id:
        try:
            parsed_start_id = uuid.UUID(start_id)
        except (ValueError, AttributeError):
            parsed_start_id = None
        if parsed_start_id and indoor.nodes.filter(pk=parsed_start_id).exists():
            params = {"start": str(parsed_start_id)}
            end_id = request.POST.get("end", "")
            try:
                if end_id and indoor.nodes.filter(pk=uuid.UUID(end_id)).exists():
                    params["end"] = end_id
            except (ValueError, AttributeError):
                pass
            target["Location"] += "?" + urlencode(params)
    return target
