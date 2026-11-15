"""Upgrade only the known star-shaped demonstration map, retaining its IDs."""
import math
from pathlib import Path

from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.rentals.models import Camera, ExitPoint, HazardZone, IndoorMap, MapEdge, MapNode, MapZone, SafetyDevice


class Command(BaseCommand):
    help = "Dựng mặt bằng mẫu có cửa và hành lang. Sao lưu trước khi đổi hình học demo."

    def add_arguments(self, parser):
        parser.add_argument("--map-id", required=True)
        parser.add_argument("--backup-dir", default="tmp/indoor-map-backups")

    @transaction.atomic
    def handle(self, *args, **options):
        indoor = IndoorMap.objects.select_for_update().get(pk=options["map_id"])
        if indoor.name == "Mặt bằng mẫu 3D · phòng studio":
            self.stdout.write("Already upgraded; keeping current map and hazards unchanged.")
            return
        if indoor.name != "Sơ đồ minh họa (không phải mặt bằng thực tế)":
            raise CommandError("Only the known seeded demonstration map can be upgraded.")
        hub = indoor.nodes.filter(label="Hành lang", kind="corridor").first()
        if not hub or any(e.is_blocked or (e.start_id != hub.id and e.end_id != hub.id)
                          for e in indoor.edges.all()):
            raise CommandError("Custom graph detected; refusing to overwrite it.")
        rooms = list(indoor.building.rooms.filter(floor=indoor.floor).order_by("number"))
        if not 1 <= len(rooms) <= 12:
            raise CommandError("This demonstration floor supports between 1 and 12 rooms.")
        records = [indoor]
        for relation in ("nodes", "edges", "zones", "exit_points", "safety_devices", "cameras", "hazards"):
            records.extend(getattr(indoor, relation).all())
        backup_dir = Path(options["backup_dir"])
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{indoor.id}-{timezone.now():%Y%m%d-%H%M%S-%f}.json"
        backup.write_text(serializers.serialize("json", records, indent=2), encoding="utf-8")
        indoor.width, indoor.height = 1200, 700
        indoor.name = "Mặt bằng mẫu 3D · phòng studio"
        indoor.save(update_fields=["width", "height", "name", "updated_at"])
        # All old edges have been positively identified as the generated star.
        indoor.edges.all().delete()

        def node(label, kind, x, y, room=None):
            query = {"room": room} if room else {"label": label}
            obj = indoor.nodes.filter(**query).first()
            if obj is None:
                obj = MapNode(indoor_map=indoor, **query)
            obj.label, obj.kind, obj.x, obj.y = label, kind, x, y
            obj.full_clean()
            obj.save()
            return obj

        def zone(name, kind, x, y, width, height, room=None):
            query = {"room": room} if room else {"name": name}
            obj = indoor.zones.filter(**query).first()
            if obj is None:
                obj = MapZone(indoor_map=indoor, **query)
            obj.name, obj.kind = name, kind
            obj.x, obj.y, obj.width, obj.height = x, y, width, height
            obj.full_clean()
            obj.save()
            return obj

        def connect(a, b):
            MapEdge.objects.get_or_create(indoor_map=indoor, start=a, end=b)

        junctions = {600: node("Hành lang", "corridor", 600, 350)}
        top = math.ceil(len(rooms) / 2)
        columns = max(3, top)
        room_width = min(240, (800 - 24 * (columns - 1)) // columns)
        for index, room in enumerate(rooms):
            upper = index < top
            count = top if upper else len(rooms) - top
            slot = index if upper else index - top
            cx = 600 if count == 1 else round(200 + room_width / 2 + slot * (800 - room_width) / (count - 1))
            y, door_y = (100, 300) if upper else (400, 400)
            zone(f"Phòng {room.number}", "room", cx - room_width // 2, y, room_width, 200, room)
            inside = node(f"Phòng {room.number}", "room", cx, y + 110, room)
            door = node(f"Cửa phòng {room.number}", "corridor", cx, door_y)
            if cx not in junctions:
                junctions[cx] = node(f"Hành lang {cx}", "corridor", cx, 350)
            connect(inside, door)
            connect(door, junctions[cx])
        for x in (200, 1000):
            junctions[x] = node(f"Sảnh {x}", "corridor", x, 350)
        ordered = sorted(junctions.values(), key=lambda n: n.x)
        for a, b in zip(ordered, ordered[1:]):
            connect(a, b)
        for old_label, new_label, x, end_x, zone_x in (
            ("Lối thoát phụ minh họa", "Lối thoát Tây", 140, 200, 80),
            ("Lối thoát minh họa", "Lối thoát Đông", 1060, 1000, 1000),
        ):
            endpoint = node(old_label, "exit", x, 350)
            endpoint.label = new_label
            endpoint.save(update_fields=["label", "updated_at"])
            connect(junctions[end_x], endpoint)
            ExitPoint.objects.update_or_create(indoor_map=indoor, node=endpoint, defaults={"name": new_label})
            zone("Lối thoát trái" if x == 140 else "Lối thoát phải", "exit", zone_x, 300, 120, 100)
        zone("Hành lang chung", "corridor", 200, 300, 800, 100)
        zone("Cầu thang Tây", "stairs", 80, 170, 120, 130)
        zone("Cầu thang Đông", "stairs", 1000, 400, 120, 130)
        if len(rooms) == 5:
            zone("Sảnh sinh hoạt", "other", 460, 400, 280, 200)
        device = indoor.safety_devices.filter(kind="extinguisher").first()
        if device:
            device.x, device.y = 240, 385
            device.save(update_fields=["x", "y", "updated_at"])
        SafetyDevice.objects.get_or_create(indoor_map=indoor, name="Bình chữa cháy Đông (mẫu)",
                                         defaults={"kind": "extinguisher", "x": 970, "y": 315})
        # The existing camera and hazard foreign keys still point to the same zones.
        for model in (MapNode, MapZone, ExitPoint, Camera, SafetyDevice, HazardZone):
            for obj in model.objects.filter(indoor_map=indoor):
                obj.full_clean()
        self.stdout.write(self.style.SUCCESS(f"Updated map {indoor.id}; backup: {backup}"))
