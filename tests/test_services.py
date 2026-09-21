from datetime import date, datetime, timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Contract, Invoice, Room, Tenant
from apps.rentals.services import activate_contract, create_monthly_invoice, record_payment
from apps.rentals.templatetags.vietnamese import vnd


class RentalServiceTests(TestCase):
    def test_vietnamese_currency_format(self):
        self.assertEqual(vnd(1_000_000), "1.000.000")
        self.assertEqual(vnd(Decimal("3250000.00")), "3.250.000")

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="owner", password="test-pass-123", role="owner")
        self.building = Building.objects.create(name="Tòa A", address="TP.HCM", owner=self.user)
        self.room = Room.objects.create(building=self.building, number="101", monthly_rent=Decimal("3000000"))
        self.tenant = Tenant.objects.create(full_name="Khách A", phone="0901", identity_number="ID001")
        self.contract = Contract.objects.create(
            code="HD001",
            room=self.room,
            representative=self.tenant,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            monthly_rent=Decimal("3000000"),
        )

    def test_activate_contract_marks_room_occupied(self):
        activate_contract(self.contract)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, Room.Status.OCCUPIED)

    def test_invoice_and_partial_payment(self):
        self.contract.status = Contract.Status.ACTIVE
        self.contract.save()
        invoice = create_monthly_invoice(self.contract, date(2026, 2, 1), date(2026, 2, 10))
        self.assertEqual(invoice.total_amount, Decimal("3000000"))
        record_payment(
            invoice=invoice,
            amount=Decimal("1000000"),
            paid_at=datetime(2026, 2, 5, tzinfo=timezone.utc),
            method="cash",
            received_by=self.user,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("1000000"))
        self.assertEqual(invoice.status, Invoice.Status.PARTIAL)
        self.assertEqual(invoice.balance, Decimal("2000000"))

    def test_authenticated_user_can_open_main_pages_and_api(self):
        self.client.force_login(self.user)
        page_names = ("dashboard", "buildings", "rooms", "tenants", "contracts", "meters", "invoices", "payments", "incidents")
        for name in page_names:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        response = self.client.get(reverse("api-dashboard-summary"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("rooms", response.json())

    def test_tenant_portal_only_exposes_own_data(self):
        tenant_user = get_user_model().objects.create_user(username="tenant", password="tenant-pass-123", role="tenant")
        self.tenant.user = tenant_user
        self.tenant.save()
        self.contract.status = Contract.Status.ACTIVE
        self.contract.save()
        invoice = create_monthly_invoice(self.contract, date(2026, 3, 1), date(2026, 3, 10))
        self.client.force_login(tenant_user)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("tenant-portal"))
        self.assertEqual(self.client.get(reverse("tenant-portal")).status_code, 200)
        self.assertContains(self.client.get(reverse("tenant-invoices")), invoice.code)
        self.assertEqual(self.client.get(reverse("rooms")).status_code, 403)

    def test_guest_can_only_browse_available_rooms(self):
        available = Room.objects.create(building=self.building, number="102", monthly_rent=Decimal("2500000"), status=Room.Status.AVAILABLE)
        occupied = Room.objects.create(building=self.building, number="103", monthly_rent=Decimal("2600000"), status=Room.Status.OCCUPIED)
        self.assertEqual(self.client.get(reverse("public-home")).status_code, 200)
        listing = self.client.get(reverse("public-rooms"))
        self.assertContains(listing, "Phòng 102")
        self.assertNotContains(listing, "Phòng 103")
        self.assertEqual(self.client.get(reverse("public-room-detail", args=[available.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse("public-room-detail", args=[occupied.id])).status_code, 404)

    def test_room_management_has_pagination_and_building_filter(self):
        second_building = Building.objects.create(name="Tòa B", address="Hà Nội", owner=self.user)
        Room.objects.bulk_create(
            [Room(building=self.building, number=f"A-{number:02d}", monthly_rent=Decimal("2000000")) for number in range(21)]
        )
        Room.objects.create(building=second_building, number="B-01", monthly_rent=Decimal("2500000"))
        self.client.force_login(self.user)

        first_page = self.client.get(reverse("rooms"))
        self.assertEqual(len(first_page.context["objects"]), 20)
        self.assertEqual(first_page.context["paginator"].count, 23)
        self.assertTrue(first_page.context["page_obj"].has_next())

        filtered = self.client.get(reverse("rooms"), {"building": second_building.id})
        self.assertEqual(filtered.context["paginator"].count, 1)
        self.assertContains(filtered, "B-01")
        self.assertNotContains(filtered, "A-01")

    def test_room_map_groups_rooms_and_filters_status(self):
        Room.objects.create(building=self.building, number="102", floor=2, monthly_rent=Decimal("2500000"), status=Room.Status.OCCUPIED)
        self.client.force_login(self.user)
        response = self.client.get(reverse("room-map"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sơ đồ phòng")
        self.assertEqual(response.context["stats"]["total"], 2)

        filtered = self.client.get(reverse("room-map"), {"status": Room.Status.OCCUPIED})
        self.assertContains(filtered, "102")
        self.assertNotContains(filtered, ">101<")
