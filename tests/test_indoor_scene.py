import io
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from apps.rentals.indoor_map import scene_for_map, shortest_exit
from apps.rentals.models import Building, HazardZone, IndoorMap, Room


class IndoorSceneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user("map-owner", role="owner")
        cls.building = Building.objects.create(name="Tòa nhà thử nghiệm", address="Địa chỉ mẫu", owner=cls.owner)
        for number in ("A01", "F1-01", "F1-02", "F1-03", "F1-04"):
            Room.objects.create(building=cls.building, floor=1, number=number, monthly_rent=3200000)
        call_command("seed_indoor_map", building_id=str(cls.building.id), stdout=io.StringIO())
        cls.indoor = IndoorMap.objects.get(building=cls.building)
        cls.old_nodes = set(cls.indoor.nodes.values_list("id", flat=True))
        cls.old_zones = set(cls.indoor.zones.values_list("id", flat=True))
        with tempfile.TemporaryDirectory() as backup_dir:
            call_command("build_demo_floorplan", map_id=str(cls.indoor.id), backup_dir=backup_dir, stdout=io.StringIO())
            cls.backup = json.loads(next(Path(backup_dir).glob("*.json")).read_text(encoding="utf-8"))
        cls.indoor.refresh_from_db()

    def start(self):
        return self.indoor.nodes.get(room__number="A01")

    def test_upgrade_preserves_existing_ids_and_backs_up(self):
        self.assertTrue(self.old_nodes.issubset(set(self.indoor.nodes.values_list("id", flat=True))))
        self.assertTrue(self.old_zones.issubset(set(self.indoor.zones.values_list("id", flat=True))))
        self.assertTrue(any(item["model"] == "rentals.mapedge" for item in self.backup))
        self.assertEqual(self.indoor.zones.filter(kind="room").count(), 5)
        self.assertEqual(self.indoor.cameras.count(), 1)

    def test_all_walk_segments_are_orthogonal_and_doors_on_boundary(self):
        for edge in self.indoor.edges.select_related("start", "end"):
            self.assertTrue(edge.start.x == edge.end.x or edge.start.y == edge.end.y)
        scene = scene_for_map(self.indoor, str(self.start().id))
        for zone in scene["zones"]:
            if zone["kind"] == "room":
                self.assertIsNotNone(zone["door"])
                self.assertIn(zone["door"]["y"], (zone["y"], zone["y"] + zone["height"]))
        self.assertTrue(scene["route"]["found"])
        self.assertGreater(scene["route"]["distance_m"], 0)
        self.assertEqual(scene["route"]["points"][1]["label"], "Cửa phòng A01")

    def test_explicit_room_destination_uses_both_doors(self):
        end = self.indoor.nodes.get(room__number="F1-04")
        route = scene_for_map(self.indoor, str(self.start().id), str(end.id))["route"]
        self.assertEqual(route["points"][-1]["id"], str(end.id))
        self.assertEqual(route["points"][-2]["label"], "Cửa phòng F1-04")

    def test_blocked_exit_recalculates_then_both_exits_clear_route(self):
        route = scene_for_map(self.indoor, str(self.start().id))["route"]
        self.assertEqual(route["exit_label"], "Lối thoát Tây")
        for name, expected in (("Lối thoát trái", True), ("Lối thoát phải", False)):
            HazardZone.objects.create(indoor_map=self.indoor, zone=self.indoor.zones.get(name=name), is_simulation=True)
            route = scene_for_map(self.indoor, str(self.start().id))["route"]
            self.assertEqual(route["found"], expected)
            if expected:
                self.assertEqual(route["exit_label"], "Lối thoát Đông")
            else:
                self.assertEqual(route["points"], [])
                self.assertIsNone(route["distance_m"])

    def test_unrelated_room_hazard_does_not_block_corridor(self):
        zone = self.indoor.zones.get(room__number="F1-01")
        HazardZone.objects.create(indoor_map=self.indoor, zone=zone, is_simulation=True)
        self.assertTrue(scene_for_map(self.indoor, str(self.start().id))["route"]["found"])
        blocked_start = self.indoor.nodes.get(room=zone.room)
        self.assertFalse(scene_for_map(self.indoor, str(blocked_start.id))["route"]["found"])

    def test_invalid_start_and_destination_and_zero_distance(self):
        self.assertFalse(scene_for_map(self.indoor, "invalid")["route"]["found"])
        self.assertFalse(scene_for_map(self.indoor, str(self.start().id), "invalid")["route"]["found"])
        scene = scene_for_map(self.indoor, str(self.start().id), str(self.start().id))
        self.assertTrue(scene["route"]["found"])
        self.assertEqual(scene["route"]["distance_m"], 0)

    def test_no_invented_scale_for_custom_map(self):
        self.indoor.name = "Mặt bằng khảo sát"
        scene = scene_for_map(self.indoor, str(self.start().id))
        self.assertIsNone(scene["route"]["distance_m"])
        self.assertFalse(scene["map"]["is_demo"])

    def test_json_and_html_scoping_and_camera_source_redaction(self):
        url = reverse("indoor-map", args=[self.indoor.id])
        self.assertEqual(self.client.get(url, {"format": "json"}).status_code, 302)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(url), 'id="indoor-scene-data"')
        response = self.client.get(url, {"format": "json", "start": str(self.start().id)})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["route"]["found"])
        self.assertNotIn("source", response.json()["cameras"][0])
        outsider = get_user_model().objects.create_user("outsider", role="owner")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(url, {"format": "json"}).status_code, 404)

    def test_hazard_json_keeps_destination_and_requires_authority(self):
        zone = self.indoor.zones.get(name="Lối thoát trái")
        url = reverse("indoor-map-toggle-hazard", args=[self.indoor.id, zone.id])
        end = self.indoor.nodes.get(room__number="F1-04")
        params = {"start": str(self.start().id), "end": str(end.id)}
        self.client.force_login(self.owner)
        response = self.client.post(url, params, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["route"]["end_id"], str(end.id))
        self.assertTrue(response.json()["route"]["found"])
        self.assertEqual(self.client.get(url).status_code, 405)
        staff = get_user_model().objects.create_user("map-staff", role="staff")
        self.building.staff.add(staff)
        self.client.force_login(staff)
        self.assertEqual(self.client.post(url, params, HTTP_ACCEPT="application/json").status_code, 403)

    def test_rerun_does_not_change_map_or_hazards(self):
        before = scene_for_map(self.indoor)
        with tempfile.TemporaryDirectory() as directory:
            call_command("build_demo_floorplan", map_id=str(self.indoor.id), backup_dir=directory, stdout=io.StringIO())
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.indoor.refresh_from_db()
        self.assertEqual(scene_for_map(self.indoor), before)

    def test_custom_map_is_never_overwritten(self):
        self.indoor.name = "Mặt bằng thật"
        self.indoor.save()
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(CommandError):
            call_command("build_demo_floorplan", map_id=str(self.indoor.id), backup_dir=directory, stdout=io.StringIO())
