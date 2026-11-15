from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.rentals.models import Camera, ExitPoint, IndoorMap, MapEdge, MapNode, MapZone, Room, SafetyDevice


class Command(BaseCommand):
    help = "Tạo một bản đồ tầng minh họa từ phòng hiện có, không thay thế mặt bằng thực tế."

    def add_arguments(self, parser):
        parser.add_argument("--building-id", help="UUID tòa nhà; mặc định chọn tòa đầu tiên có phòng")
        parser.add_argument("--floor", type=int, default=1)

    @transaction.atomic
    def handle(self, *args, **options):
        rooms = Room.objects.select_related("building").filter(floor=options["floor"])
        if options["building_id"]:
            rooms = rooms.filter(building_id=options["building_id"])
        first = rooms.order_by("building__name", "number").first()
        if first is None:
            raise CommandError("No rooms on the selected floor.")
        rooms = list(rooms.filter(building_id=first.building_id).order_by("number"))
        existing = IndoorMap.objects.filter(building_id=first.building_id, floor=options["floor"]).first()
        if existing:
            if "minh họa" in existing.name.lower():
                self.enrich_demo(existing, rooms)
                self.stdout.write("Updated existing demo map with zones, exits and devices.")
            else:
                self.stdout.write("A real map already exists; leaving it unchanged.")
            return
        indoor = IndoorMap.objects.create(
            building_id=first.building_id,
            floor=options["floor"],
            name="Sơ đồ minh họa (không phải mặt bằng thực tế)",
            width=1000,
            height=600,
        )
        count = len(rooms)
        corridor = MapNode.objects.create(
            indoor_map=indoor, label="Hành lang", kind=MapNode.Kind.CORRIDOR, x=500, y=350
        )
        exit_node = MapNode.objects.create(
            indoor_map=indoor, label="Lối thoát minh họa", kind=MapNode.Kind.EXIT, x=920, y=350
        )
        MapEdge.objects.create(indoor_map=indoor, start=corridor, end=exit_node)
        for index, room in enumerate(rooms):
            x = round(100 + index * 800 / max(count - 1, 1))
            node = MapNode.objects.create(
                indoor_map=indoor, label=f"Phòng {room.number}", kind=MapNode.Kind.ROOM,
                room=room, x=x, y=130,
            )
            MapEdge.objects.create(indoor_map=indoor, start=node, end=corridor)
        self.enrich_demo(indoor, rooms)
        self.stdout.write(self.style.SUCCESS(f"Created demo indoor map: {indoor.id}"))

    def enrich_demo(self, indoor, rooms):
        corridor = indoor.nodes.get(label="Hành lang", kind=MapNode.Kind.CORRIDOR)
        right_exit = indoor.nodes.get(label="Lối thoát minh họa", kind=MapNode.Kind.EXIT)
        left_exit, _ = MapNode.objects.get_or_create(
            indoor_map=indoor, label="Lối thoát phụ minh họa", kind=MapNode.Kind.EXIT,
            defaults={"x": 20, "y": 350},
        )
        if left_exit.x == 80:
            left_exit.x = 20
            left_exit.save(update_fields=["x", "updated_at"])
        MapEdge.objects.get_or_create(indoor_map=indoor, start=corridor, end=left_exit)
        ExitPoint.objects.get_or_create(indoor_map=indoor, node=right_exit, defaults={"name": "Lối thoát phải (mô phỏng)"})
        ExitPoint.objects.get_or_create(indoor_map=indoor, node=left_exit, defaults={"name": "Lối thoát trái (mô phỏng)"})
        MapZone.objects.get_or_create(
            indoor_map=indoor, name="Hành lang chung", kind=MapZone.Kind.CORRIDOR,
            defaults={"x": 150, "y": 305, "width": 700, "height": 90},
        )
        MapZone.objects.get_or_create(
            indoor_map=indoor, name="Lối thoát trái", kind=MapZone.Kind.EXIT,
            defaults={"x": 5, "y": 305, "width": 140, "height": 90},
        )
        right_zone, _ = MapZone.objects.get_or_create(
            indoor_map=indoor, name="Lối thoát phải", kind=MapZone.Kind.EXIT,
            defaults={"x": 855, "y": 305, "width": 140, "height": 90},
        )
        for room in rooms:
            node = indoor.nodes.get(room=room)
            MapZone.objects.get_or_create(
                indoor_map=indoor, room=room, kind=MapZone.Kind.ROOM,
                defaults={"name": f"Phòng {room.number}", "x": max(0, node.x - 55), "y": 75, "width": 110, "height": 110},
            )
        SafetyDevice.objects.get_or_create(
            indoor_map=indoor, name="Bình chữa cháy (mô phỏng)",
            defaults={"kind": SafetyDevice.Kind.EXTINGUISHER, "x": 350, "y": 350},
        )
        Camera.objects.get_or_create(
            indoor_map=indoor, name="Webcam mô phỏng",
            defaults={"zone": right_zone, "source": "webcam 0"},
        )
