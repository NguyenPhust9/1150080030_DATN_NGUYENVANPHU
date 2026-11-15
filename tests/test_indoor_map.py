from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.rentals.indoor_map import shortest_exit


class IndoorMapRoutingTests(SimpleTestCase):
    def test_route_avoids_blocked_edge_and_finds_exit(self):
        nodes = [
            SimpleNamespace(id="room", x=0, y=0, kind="room", is_blocked=False),
            SimpleNamespace(id="hall", x=10, y=0, kind="corridor", is_blocked=False),
            SimpleNamespace(id="exit", x=20, y=0, kind="exit", is_blocked=False),
        ]
        edges = [
            SimpleNamespace(start_id="room", end_id="exit", is_blocked=True),
            SimpleNamespace(start_id="room", end_id="hall", is_blocked=False),
            SimpleNamespace(start_id="hall", end_id="exit", is_blocked=False),
        ]
        self.assertEqual(shortest_exit(nodes, edges, "room"), ["room", "hall", "exit"])
        nodes[1].is_blocked = True
        self.assertEqual(shortest_exit(nodes, edges, "room"), [])

    def test_hazard_zone_switches_to_other_exit(self):
        nodes = [
            SimpleNamespace(id="room", x=0, y=0, kind="room", is_blocked=False),
            SimpleNamespace(id="near_exit", x=10, y=0, kind="exit", is_blocked=False),
            SimpleNamespace(id="far_exit", x=0, y=20, kind="exit", is_blocked=False),
        ]
        edges = [
            SimpleNamespace(start_id="room", end_id="near_exit", is_blocked=False),
            SimpleNamespace(start_id="room", end_id="far_exit", is_blocked=False),
        ]
        hazard = SimpleNamespace(x=7, y=0, width=2, height=3)
        self.assertEqual(shortest_exit(nodes, edges, "room"), ["room", "near_exit"])
        self.assertEqual(shortest_exit(nodes, edges, "room", [hazard]), ["room", "far_exit"])
