from datetime import date, timedelta
from html import unescape
import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Contract, Room, Tenant


class ContractListingTests(TestCase):
    """Contract cards and totals follow effective dates and operator access."""

    today = date(2026, 11, 18)

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="contract-list-owner", role="owner")
        cls.other_owner = User.objects.create_user(username="contract-list-other", role="owner")
        cls.staff = User.objects.create_user(username="contract-list-staff", role="staff")
        cls.building = Building.objects.create(name="North Annex", address="North", owner=cls.owner)
        cls.second_building = Building.objects.create(name="South Court", address="South", owner=cls.owner)
        cls.foreign_building = Building.objects.create(name="Hidden building", address="Hidden", owner=cls.other_owner)
        cls.building.staff.add(cls.staff)

        cls.normal = cls.make_contract("NORMAL", -100, 100)
        cls.expiring = cls.make_contract("EXPIRING", -60, 30)
        cls.ending = cls.make_contract("ENDING", -30, 0)
        cls.same_day = cls.make_contract("SAME-DAY", 0, 0)
        cls.stale_active = cls.make_contract("STALE-ACTIVE", -90, -1)
        cls.expired = cls.make_contract("EXPIRED", -100, -30, Contract.Status.EXPIRED)
        cls.draft = cls.make_contract("DRAFT", -100, -30, Contract.Status.DRAFT)
        cls.terminated = cls.make_contract("TERMINATED", -100, 100, Contract.Status.TERMINATED)
        cls.cancelled = cls.make_contract("CANCELLED", -100, -30, Contract.Status.CANCELLED)
        cls.upcoming = cls.make_contract("UPCOMING", 1, 91)
        cls.second = cls.make_contract("SECOND", -100, 100, building=cls.second_building)
        cls.hidden = cls.make_contract("HIDDEN", -100, 100, building=cls.foreign_building)

    @classmethod
    def make_contract(cls, suffix, start_offset, end_offset, status=Contract.Status.ACTIVE, building=None):
        building = building or cls.building
        room = Room.objects.create(building=building, number=f"ROOM-{suffix}", monthly_rent=3000000)
        tenant = Tenant.objects.create(owner=building.owner, full_name=f"Resident of {suffix}")
        return Contract.objects.create(
            code=f"LEASE-{suffix}", room=room, representative=tenant,
            start_date=cls.today + timedelta(days=start_offset),
            end_date=cls.today + timedelta(days=end_offset),
            monthly_rent=3000000, deposit_amount=3000000, status=status,
        )

    def setUp(self):
        self.client.force_login(self.owner)
        clock = patch("django.utils.timezone.localdate", return_value=self.today)
        clock.start()
        self.addCleanup(clock.stop)

    def get_list(self, **filters):
        response = self.client.get(reverse("contracts"), filters)
        self.assertEqual(response.status_code, 200)
        return response

    def visible_ids(self, response):
        return {contract.pk for contract in response.context["objects"]}

    def test_owner_metrics_classify_dates_without_counting_inactive_states(self):
        response = self.get_list()
        self.assertEqual(response.context["contract_metrics"], {
            "total_count": 11, "active_count": 5, "expiring_count": 3, "expired_count": 2,
        })
        self.assertNotContains(response, self.hidden.code)
        self.assertNotIn(self.foreign_building, response.context["buildings"])
        # Rendering a date-derived status does not rewrite stored contracts.
        self.stale_active.refresh_from_db()
        self.assertEqual(self.stale_active.status, Contract.Status.ACTIVE)

    def test_staff_only_sees_contracts_and_counts_for_assigned_buildings(self):
        self.client.force_login(self.staff)
        response = self.get_list()
        self.assertEqual(response.context["contract_metrics"], {
            "total_count": 10, "active_count": 4, "expiring_count": 3, "expired_count": 2,
        })
        self.assertEqual(set(response.context["buildings"]), {self.building})
        self.assertNotContains(response, self.second.code)
        self.assertNotContains(response, self.hidden.code)

    def test_foreign_building_filter_cannot_expose_contracts_or_metrics(self):
        response = self.get_list(building=str(self.foreign_building.pk))
        self.assertEqual(response.context["paginator"].count, 0)
        self.assertTrue(all(value == 0 for value in response.context["contract_metrics"].values()))
        self.assertNotContains(response, self.hidden.code)

    def test_effective_status_filters_include_date_boundaries(self):
        expected = {
            "active": {self.normal.pk, self.expiring.pk, self.ending.pk, self.same_day.pk, self.second.pk},
            "expiring": {self.expiring.pk, self.ending.pk, self.same_day.pk},
            "expired": {self.expired.pk, self.stale_active.pk},
            "upcoming": {self.upcoming.pk},
            "draft": {self.draft.pk},
            "terminated": {self.terminated.pk},
            "cancelled": {self.cancelled.pk},
        }
        for status, expected_ids in expected.items():
            with self.subTest(status=status):
                response = self.get_list(status=status)
                self.assertEqual(self.visible_ids(response), expected_ids)
                self.assertEqual(response.context["status"], status)
                self.assertEqual(response.context["contract_metrics"]["total_count"], len(expected_ids))

    def test_search_finds_code_room_tenant_and_building(self):
        for query, expected_ids in (
            ("LEASE-NORMAL", {self.normal.pk}),
            ("ROOM-NORMAL", {self.normal.pk}),
            ("Resident of NORMAL", {self.normal.pk}),
            ("South Court", {self.second.pk}),
        ):
            with self.subTest(query=query):
                response = self.get_list(q=query)
                self.assertEqual(self.visible_ids(response), expected_ids)
                self.assertEqual(response.context["contract_metrics"]["total_count"], len(expected_ids))

    def test_combined_filters_control_both_cards_and_metrics(self):
        response = self.get_list(q="ROOM-EXPIRING", building=str(self.building.pk), status="expiring")
        self.assertEqual(self.visible_ids(response), {self.expiring.pk})
        self.assertEqual(response.context["contract_metrics"], {
            "total_count": 1, "active_count": 1, "expiring_count": 1, "expired_count": 0,
        })
        response = self.get_list(q="ROOM-EXPIRING", building=str(self.second_building.pk), status="expiring")
        self.assertEqual(response.context["paginator"].count, 0)
        self.assertTrue(all(value == 0 for value in response.context["contract_metrics"].values()))

    def test_malformed_building_and_unknown_status_reset_safely(self):
        response = self.get_list(building="not-a-uuid", status="not-a-status")
        self.assertEqual(response.context["selected_building"], "")
        self.assertEqual(response.context["status"], "")
        self.assertEqual(response.context["contract_metrics"]["total_count"], 11)
        self.assertNotContains(response, self.hidden.code)

    def test_pagination_keeps_full_filtered_metrics_and_filter_links(self):
        for index in range(25):
            self.make_contract(f"PAGING-{index}", -100, 100)
        filters = {"q": "PAGING", "building": str(self.building.pk), "status": "active"}
        first_page = self.get_list(**filters)
        second_page = self.get_list(page="2", **filters)
        expected = {"total_count": 25, "active_count": 25, "expiring_count": 0, "expired_count": 0}
        self.assertEqual(first_page.context["contract_metrics"], expected)
        self.assertEqual(second_page.context["contract_metrics"], expected)
        self.assertEqual(len(first_page.context["objects"]), 20)
        self.assertEqual(len(second_page.context["objects"]), 5)
        self.assertTrue(self.visible_ids(first_page).isdisjoint(self.visible_ids(second_page)))
        links = [
            parse_qs(urlsplit(unescape(href)).query)
            for href in re.findall(r'href="([^"]+)"', first_page.content.decode())
        ]
        next_links = [params for params in links if params.get("page") == ["2"]]
        self.assertTrue(next_links)
        for params in next_links:
            for key, value in filters.items():
                self.assertEqual(params.get(key), [value])

    def test_remaining_time_handles_future_expired_and_same_day_contracts(self):
        cards = {item.pk: item.listing for item in self.get_list().context["objects"]}
        normal = cards[self.normal.pk]
        self.assertEqual(normal["remaining_days"], 100)
        self.assertEqual(normal["total_days"], 200)
        self.assertEqual(normal["remaining_percent"], 50)
        self.assertEqual(cards[self.expiring.pk]["remaining_days"], 30)
        for contract in (self.ending, self.same_day, self.stale_active, self.expired):
            with self.subTest(contract=contract.code):
                self.assertEqual(cards[contract.pk]["remaining_days"], 0)
                self.assertEqual(cards[contract.pk]["remaining_percent"], 0)
        self.assertEqual(cards[self.same_day.pk]["total_days"], 0)
        self.assertEqual(cards[self.upcoming.pk]["status_key"], "upcoming")
        self.assertEqual(cards[self.upcoming.pk]["remaining_days"], 90)
        self.assertEqual(cards[self.upcoming.pk]["remaining_percent"], 100)
        for contract in (self.draft, self.terminated, self.cancelled):
            self.assertEqual(cards[contract.pk]["remaining_percent"], 0)
        for presentation in cards.values():
            self.assertGreaterEqual(presentation["remaining_percent"], 0)
            self.assertLessEqual(presentation["remaining_percent"], 100)

    def test_contract_cards_keep_detail_tenant_and_draft_edit_actions(self):
        response = self.get_list()
        for label in ("Tổng hợp đồng", "Hoạt động", "Sắp hết hạn", "Đã hết hạn", "Danh sách hợp đồng"):
            self.assertContains(response, label)
        for field in ("q", "building", "status"):
            self.assertContains(response, f'name="{field}"')
        self.assertContains(response, f'href="{reverse("contract-create")}"')
        for contract in (self.normal, self.draft):
            self.assertContains(response, f'href="{reverse("contract-detail", args=[contract.pk])}"')
            self.assertContains(response, f'href="{reverse("tenant-detail", args=[contract.representative_id])}"')
        self.assertContains(response, f'href="{reverse("contract-update", args=[self.draft.pk])}"')
        self.assertNotContains(response, f'href="{reverse("contract-update", args=[self.normal.pk])}"')
