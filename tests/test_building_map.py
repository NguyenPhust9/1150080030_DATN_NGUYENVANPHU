from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.building_map import building_scene, floor_layouts
from apps.rentals.models import Building, Camera, Contract, HazardZone, IndoorMap, MapEdge, MapNode, MapZone, Room, Tenant


class BuildingMapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user("architecture-owner", role="owner")
        cls.building = Building.objects.create(name="An Tâm", address="Test", owner=cls.owner)
        cls.rooms = {}
        for floor in range(1, 6):
            for slot in range(1, 6):
                number = f"A{floor}0{slot}"
                cls.rooms[number] = Room.objects.create(building=cls.building, floor=floor, number=number, monthly_rent=3000000)
        cls.indoor = IndoorMap.objects.create(building=cls.building, floor=1)
        cls.zone = MapZone.objects.create(indoor_map=cls.indoor, room=cls.rooms["A101"], name="Phòng A101", kind="room", x=100, y=100, width=150, height=200)
        cls.camera = Camera.objects.create(indoor_map=cls.indoor, zone=cls.zone, name="Camera cửa phòng", source="private-source")
        cls.url = reverse("building-indoor-map", args=[cls.building.id])

    def scene(self, **params):
        return building_scene(self.building, self.owner, params)

    def room_id(self, number):
        return f"room:{self.rooms[number].id}"

    def test_all_five_floors_come_from_rooms_not_saved_maps(self):
        scene = self.scene()
        self.assertEqual([floor["number"] for floor in scene["floors"]], [1, 2, 3, 4, 5])
        self.assertEqual([len(floor["rooms"]) for floor in scene["floors"]], [5]*5)
        self.assertEqual(IndoorMap.objects.count(), 1)
        self.assertEqual(MapZone.objects.count(), 1)
        self.assertNotIn("source", scene["cameras"][0])

    def test_layout_matches_tour_coordinates_and_has_only_ground_entrance(self):
        scene = self.scene()
        for floor in scene["floors"]:
            self.assertEqual([room["x"] for room in floor["rooms"]], [0, -3.6, -7.2, -10.8, -14.4])
            self.assertEqual(floor["lift_x"], -18.03)
            self.assertAlmostEqual(floor["elevation"], (floor["number"]-1)*4.8)
        self.assertEqual([f["number"] for f in scene["floors"] if f["entrance_x"] is not None], [1])
        self.assertEqual([p["kind"] for p in scene["places"]].count("entrance"), 1)
        self.assertFalse(any(p["kind"] == "stairs" for p in scene["places"]))

    def test_normal_route_reaches_fifth_floor_via_lift(self):
        route = self.scene(start=self.room_id("A101"), end=self.room_id("A505"))["route"]
        self.assertTrue(route["found"])
        self.assertEqual(route["points"][0]["id"], self.room_id("A101"))
        self.assertEqual(route["points"][-1]["id"], self.room_id("A505"))
        self.assertEqual([p["floor"] for p in route["points"] if p["kind"] == "lift"], [1, 2, 3, 4, 5])
        for a, b in zip(route["points"], route["points"][1:]):
            self.assertEqual(sum(a[key] != b[key] for key in ("x", "y", "z")), 1)
            if a["floor"] != b["floor"]:
                self.assertEqual((a["kind"], b["kind"]), ("lift", "lift"))

    def test_same_floor_route_uses_both_room_doors(self):
        route = self.scene(start=self.room_id("A501"), end=self.room_id("A505"))["route"]
        self.assertTrue(route["found"])
        self.assertEqual(route["points"][1]["label"], "Cửa A501")
        self.assertEqual(route["points"][-2]["label"], "Cửa A505")
        self.assertEqual(route["transfers"], [])

    def test_evacuation_never_uses_lift(self):
        route = self.scene(start=self.room_id("A505"), mode="evacuation")["route"]
        self.assertFalse(route["found"])
        self.assertEqual(route["points"], [])
        self.assertIn("Không dùng thang máy", route["reason"])
        ground = self.scene(start=self.room_id("A101"), mode="evacuation")["route"]
        self.assertTrue(ground["found"])
        self.assertEqual(ground["points"][-1]["kind"], "entrance")

    def test_room_hazard_is_not_projected_onto_other_floors(self):
        HazardZone.objects.create(indoor_map=self.indoor, zone=self.zone, is_simulation=True)
        scene = self.scene(start=self.room_id("A501"), end=self.room_id("A505"))
        self.assertTrue(scene["route"]["found"])
        flagged = [room["number"] for floor in scene["floors"] for room in floor["rooms"] if room["hazard"]]
        self.assertEqual(flagged, ["A101"])
        self.assertFalse(self.scene(start=self.room_id("A101"))["route"]["found"])
        self.assertFalse(self.scene(start=self.room_id("A201"), end=self.room_id("A505"))["route"]["found"])

    def test_unmapped_hazard_keeps_data_and_blocks_affected_floor(self):
        zone = MapZone.objects.create(indoor_map=self.indoor, name="Lối thoát cũ", kind="exit", x=30, y=10, width=70, height=200)
        hazard = HazardZone.objects.create(indoor_map=self.indoor, zone=zone, is_simulation=False)
        scene = self.scene(start=self.room_id("A103"))
        self.assertFalse(scene["route"]["found"])
        self.assertTrue(scene["warnings"])
        self.assertTrue(HazardZone.objects.get(id=hazard.id).is_active)
        zone.refresh_from_db()
        self.assertEqual((zone.x, zone.y), (30, 10))

    def test_get_requests_do_not_write_or_migrate_old_maps(self):
        self.client.force_login(self.owner)
        before = list(MapZone.objects.values())
        for params in ({}, {"format": "json", "floor": "5"}, {"floor": "not-a-number"}):
            self.assertEqual(self.client.get(self.url, params).status_code, 200)
        self.assertEqual(list(MapZone.objects.values()), before)
        self.assertEqual(IndoorMap.objects.count(), 1)
        self.assertEqual(HazardZone.objects.count(), 0)
        self.assertEqual(self.client.get(self.url, {"format": "json", "floor": "999"}).json()["floor"], 1)

    def test_building_without_any_saved_map_still_opens(self):
        self.indoor.delete()
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("indoor-map-list")), self.url)
        response = self.client.get(self.url, {"format": "json"})
        self.assertEqual(len(response.json()["floors"]), 5)
        self.assertEqual(IndoorMap.objects.count(), 0)

    def test_outsider_cannot_open_or_route_building(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        outsider = get_user_model().objects.create_user("outsider-map", role="owner")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(self.url, {"format": "json"}).status_code, 404)
        self.assertFalse(self.scene(start="room:unknown", end=self.room_id("A105"))["route"]["found"])

    def test_same_owner_other_building_rooms_are_excluded(self):
        building = Building.objects.create(name="Other", address="Test", owner=self.owner)
        other = Room.objects.create(building=building, floor=1, number="A101", monthly_rent=3000000)
        scene = self.scene(start=f"room:{other.id}", end=self.room_id("A101"))
        self.assertFalse(scene["route"]["found"])
        self.assertNotIn(str(other.id), [room["room_id"] for floor in scene["floors"] for room in floor["rooms"]])

    def test_sparse_known_rooms_keep_tour_slots(self):
        floor = floor_layouts([self.rooms["A105"]])[0]
        self.assertEqual(floor["rooms"][0]["x"], -14.4)
        self.assertEqual(floor["lift_x"], -18.03)

    def test_existing_blocked_nodes_and_edges_remain_blocked(self):
        room_node = MapNode.objects.create(indoor_map=self.indoor, room=self.rooms["A101"], label="A101", kind="room", x=100, y=100, is_blocked=True)
        self.assertFalse(self.scene(start=self.room_id("A101"))["route"]["found"])
        self.assertTrue(self.scene(start=self.room_id("A103"))["route"]["found"])
        hall = MapNode.objects.create(indoor_map=self.indoor, label="Hành lang", x=100, y=300)
        MapEdge.objects.create(indoor_map=self.indoor, start=room_node, end=hall, is_blocked=True)
        self.assertFalse(self.scene(start=self.room_id("A103"))["route"]["found"])
        self.assertTrue(self.scene()["warnings"])

    def test_tenant_only_sees_own_room_and_no_neighbour_camera(self):
        user = get_user_model().objects.create_user("map-tenant", role="tenant")
        tenant = Tenant.objects.create(user=user, full_name="Khách thử", phone="0900000099", owner=self.owner)
        Contract.objects.create(code="MAP-TENANT", room=self.rooms["A105"], representative=tenant,
                                start_date=date(2026, 1, 1), end_date=date(2027, 1, 1), monthly_rent=3000000, status="active")
        self.client.force_login(user)
        scene = self.client.get(self.url, {"format": "json", "end": self.room_id("A101"), "start": self.room_id("A105")}).json()
        self.assertEqual([r["number"] for f in scene["floors"] for r in f["rooms"]], ["A105"])
        self.assertEqual(scene["cameras"], [])
        self.assertFalse(scene["route"]["found"])
