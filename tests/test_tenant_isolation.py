from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.rentals.forms import BuildingForm, ContractForm, MeterReadingForm, RoomForm
from apps.rentals.models import (
    Building,
    Contract,
    Incident,
    Invoice,
    MeterReading,
    Notification,
    Payment,
    Room,
    Tenant,
)
from apps.rentals.permissions import (
    get_accessible_buildings,
    get_accessible_contracts,
    get_accessible_incidents,
    get_accessible_invoices,
    get_accessible_meter_readings,
    get_accessible_notifications,
    get_accessible_payments,
    get_accessible_rooms,
    get_accessible_tenants,
)

User = get_user_model()


class TenantAndOwnerIsolationTests(TestCase):
    def setUp(self):
        # 1. Admin
        self.admin = User.objects.create_user(
            username="admin_user", password="PassWord123!", role="admin"
        )

        # 2. Owner 1 & Owner 2
        self.owner_1 = User.objects.create_user(
            username="owner_1", password="PassWord123!", role="owner"
        )
        self.owner_2 = User.objects.create_user(
            username="owner_2", password="PassWord123!", role="owner"
        )

        # 3. Buildings
        self.building_1 = Building.objects.create(
            name="Tòa Nhà Owner 1", address="Quận 1, TP.HCM", owner=self.owner_1
        )
        self.building_2 = Building.objects.create(
            name="Tòa Nhà Owner 2", address="Quận 7, TP.HCM", owner=self.owner_2
        )

        # 4. Staff 1 (assigned to owner_1) & Staff 2 (assigned to building_2)
        self.staff_1 = User.objects.create_user(
            username="staff_1",
            password="PassWord123!",
            role="staff",
            managed_owner=self.owner_1,
        )
        self.staff_2 = User.objects.create_user(
            username="staff_2",
            password="PassWord123!",
            role="staff",
        )
        self.building_2.staff.add(self.staff_2)

        # 5. Rooms
        self.room_1 = Room.objects.create(
            building=self.building_1, number="101", floor=1, monthly_rent=Decimal("4000000")
        )
        self.room_2 = Room.objects.create(
            building=self.building_2, number="202", floor=2, monthly_rent=Decimal("5000000")
        )

        # 6. Tenants
        self.user_a = User.objects.create_user(
            username="tenant_a", password="PassWord123!", role="tenant"
        )
        self.tenant_a = Tenant.objects.create(
            user=self.user_a,
            owner=self.owner_1,
            full_name="Nguyễn Văn A",
            phone="0901000001",
            identity_number="111111111111",
        )

        self.user_b = User.objects.create_user(
            username="tenant_b", password="PassWord123!", role="tenant"
        )
        self.tenant_b = Tenant.objects.create(
            user=self.user_b,
            owner=self.owner_2,
            full_name="Trần Thị B",
            phone="0902000002",
            identity_number="222222222222",
        )

        # 7. Contracts
        self.contract_a = Contract.objects.create(
            code="HD-001",
            room=self.room_1,
            representative=self.tenant_a,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=150),
            monthly_rent=Decimal("4000000"),
            deposit_amount=Decimal("4000000"),
            status=Contract.Status.ACTIVE,
        )
        self.contract_b = Contract.objects.create(
            code="HD-002",
            room=self.room_2,
            representative=self.tenant_b,
            start_date=date.today() - timedelta(days=20),
            end_date=date.today() + timedelta(days=160),
            monthly_rent=Decimal("5000000"),
            deposit_amount=Decimal("5000000"),
            status=Contract.Status.ACTIVE,
        )

        # 8. Meter Readings
        period = date.today().replace(day=1)
        self.meter_1 = MeterReading.objects.create(
            room=self.room_1,
            meter_type=MeterReading.MeterType.ELECTRICITY,
            period=period,
            previous_value=Decimal("100"),
            current_value=Decimal("150"),
            recorded_by=self.owner_1,
        )
        self.meter_2 = MeterReading.objects.create(
            room=self.room_2,
            meter_type=MeterReading.MeterType.ELECTRICITY,
            period=period,
            previous_value=Decimal("200"),
            current_value=Decimal("260"),
            recorded_by=self.owner_2,
        )

        # 9. Invoices & Payments
        self.invoice_a = Invoice.objects.create(
            code="HD001-T10",
            contract=self.contract_a,
            period=period,
            issued_date=date.today(),
            subtotal=Decimal("4000000"),
            total_amount=Decimal("4000000"),
            paid_amount=Decimal("2000000"),
            due_date=date.today() + timedelta(days=5),
            status=Invoice.Status.PARTIAL,
        )
        self.payment_a = Payment.objects.create(
            invoice=self.invoice_a,
            amount=Decimal("2000000"),
            paid_at=timezone.now(),
            method=Payment.Method.TRANSFER,
            reference="VCB123456",
            received_by=self.owner_1,
        )

        self.invoice_b = Invoice.objects.create(
            code="HD002-T10",
            contract=self.contract_b,
            period=period,
            issued_date=date.today(),
            subtotal=Decimal("5000000"),
            total_amount=Decimal("5000000"),
            paid_amount=Decimal("5000000"),
            due_date=date.today() + timedelta(days=5),
            status=Invoice.Status.PAID,
        )
        self.payment_b = Payment.objects.create(
            invoice=self.invoice_b,
            amount=Decimal("5000000"),
            paid_at=timezone.now(),
            method=Payment.Method.CASH,
            reference="TM002",
            received_by=self.owner_2,
        )

        # 10. Incidents & Notifications
        self.incident_a = Incident.objects.create(
            room=self.room_1,
            reported_by=self.tenant_a,
            title="Hỏng đèn phòng 101",
            description="Đèn nhấp nháy",
        )
        self.incident_b = Incident.objects.create(
            room=self.room_2,
            reported_by=self.tenant_b,
            title="Rò nước phòng 202",
            description="Vòi nước rỉ",
        )
        self.notif_a = Notification.objects.create(
            title="Thông báo tòa 1",
            content="Nội dung 1",
            recipient=self.user_a,
            building=self.building_1,
            created_by=self.owner_1,
        )
        self.notif_b = Notification.objects.create(
            title="Thông báo tòa 2",
            content="Nội dung 2",
            recipient=self.user_b,
            building=self.building_2,
            created_by=self.owner_2,
        )

    def test_admin_sees_all_data(self):
        self.assertEqual(get_accessible_buildings(self.admin).count(), 2)
        self.assertEqual(get_accessible_rooms(self.admin).count(), 2)
        self.assertEqual(get_accessible_tenants(self.admin).count(), 2)
        self.assertEqual(get_accessible_contracts(self.admin).count(), 2)
        self.assertEqual(get_accessible_meter_readings(self.admin).count(), 2)
        self.assertEqual(get_accessible_invoices(self.admin).count(), 2)
        self.assertEqual(get_accessible_payments(self.admin).count(), 2)
        self.assertEqual(get_accessible_incidents(self.admin).count(), 2)
        self.assertEqual(get_accessible_notifications(self.admin).count(), 2)

    def test_owner_isolation_across_all_models(self):
        # Owner 1 only sees Owner 1's data
        self.assertQuerySetEqual(
            get_accessible_buildings(self.owner_1), [self.building_1], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_rooms(self.owner_1), [self.room_1], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_tenants(self.owner_1), [self.tenant_a], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_contracts(self.owner_1), [self.contract_a], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_meter_readings(self.owner_1), [self.meter_1], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_invoices(self.owner_1), [self.invoice_a], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_payments(self.owner_1), [self.payment_a], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_incidents(self.owner_1), [self.incident_a], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_notifications(self.owner_1), [self.notif_a], ordered=False
        )

        # Owner 2 only sees Owner 2's data
        self.assertQuerySetEqual(
            get_accessible_buildings(self.owner_2), [self.building_2], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_rooms(self.owner_2), [self.room_2], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_tenants(self.owner_2), [self.tenant_b], ordered=False
        )

    def test_staff_isolation_by_owner_and_assigned_building(self):
        # Staff 1 assigned via managed_owner=owner_1
        self.assertQuerySetEqual(
            get_accessible_buildings(self.staff_1), [self.building_1], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_rooms(self.staff_1), [self.room_1], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_invoices(self.staff_1), [self.invoice_a], ordered=False
        )

        # Staff 2 assigned via building_2.staff
        self.assertQuerySetEqual(
            get_accessible_buildings(self.staff_2), [self.building_2], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_rooms(self.staff_2), [self.room_2], ordered=False
        )
        self.assertQuerySetEqual(
            get_accessible_invoices(self.staff_2), [self.invoice_b], ordered=False
        )

    def test_owner_and_staff_cannot_view_or_edit_other_owner_resources_via_url(self):
        # Owner 1 listing pages only contain Owner 1's objects
        self.client.force_login(self.owner_1)
        res_buildings = self.client.get(reverse("buildings"))
        self.assertContains(res_buildings, "Tòa Nhà Owner 1")
        self.assertNotContains(res_buildings, "Tòa Nhà Owner 2")

        res_rooms = self.client.get(reverse("rooms"))
        self.assertContains(res_rooms, "101")
        self.assertNotContains(res_rooms, "202")

        res_tenants = self.client.get(reverse("tenants"))
        self.assertContains(res_tenants, "Nguyễn Văn A")
        self.assertNotContains(res_tenants, "Trần Thị B")

        res_contracts = self.client.get(reverse("contracts"))
        self.assertContains(res_contracts, "HD-001")
        self.assertNotContains(res_contracts, "HD-002")

        res_invoices = self.client.get(reverse("invoices"))
        self.assertContains(res_invoices, "HD001-T10")
        self.assertNotContains(res_invoices, "HD002-T10")

        res_payments = self.client.get(reverse("payments"))
        self.assertContains(res_payments, "VCB123456")
        self.assertNotContains(res_payments, "TM002")

        res_incidents = self.client.get(reverse("incidents"))
        self.assertContains(res_incidents, "Hỏng đèn phòng 101")
        self.assertNotContains(res_incidents, "Rò nước phòng 202")

        # Direct UUID access to Owner 2's building/room/API must return 404
        self.assertEqual(
            self.client.get(reverse("building-update", args=[self.building_2.id])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("room-update", args=[self.room_2.id])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("api-room-detail", args=[self.room_2.id])).status_code,
            404,
        )

        # Staff 1 cannot edit Owner 2's room
        self.client.force_login(self.staff_1)
        self.assertEqual(
            self.client.get(reverse("room-update", args=[self.room_2.id])).status_code,
            404,
        )

    def test_form_dropdowns_only_show_accessible_objects(self):
        room_form = RoomForm(user=self.owner_1)
        self.assertQuerySetEqual(
            room_form.fields["building"].queryset, [self.building_1], ordered=False
        )

        contract_form = ContractForm(user=self.owner_1)
        self.assertQuerySetEqual(
            contract_form.fields["room"].queryset, [self.room_1], ordered=False
        )
        self.assertQuerySetEqual(
            contract_form.fields["representative"].queryset, [self.tenant_a], ordered=False
        )

        meter_form = MeterReadingForm(user=self.staff_2)
        self.assertQuerySetEqual(
            meter_form.fields["room"].queryset, [self.room_2], ordered=False
        )

        building_form = BuildingForm(user=self.owner_1)
        self.assertQuerySetEqual(
            building_form.fields["owner"].queryset, [self.owner_1], ordered=False
        )

    def test_tenant_only_sees_own_rooms_contracts_invoices_payments_incidents_notifications(self):
        self.client.force_login(self.user_a)
        res_rooms = self.client.get(reverse("tenant-rooms"))
        self.assertEqual(res_rooms.status_code, 200)
        self.assertContains(res_rooms, "Phòng 101")
        self.assertNotContains(res_rooms, "Phòng 202")

        res_contracts = self.client.get(reverse("tenant-contracts"))
        self.assertEqual(res_contracts.status_code, 200)
        self.assertContains(res_contracts, "HD-001")
        self.assertNotContains(res_contracts, "HD-002")

        res_invoices = self.client.get(reverse("tenant-invoices"))
        self.assertEqual(res_invoices.status_code, 200)
        self.assertContains(res_invoices, "HD001-T10")
        self.assertNotContains(res_invoices, "HD002-T10")

        # Tenant A cannot view Tenant B's invoice detail by UUID
        self.assertEqual(
            self.client.get(reverse("tenant-invoice-detail", args=[self.invoice_a.id])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("tenant-invoice-detail", args=[self.invoice_b.id])).status_code,
            404,
        )

        res_payments = self.client.get(reverse("tenant-payments"))
        self.assertEqual(res_payments.status_code, 200)
        self.assertContains(res_payments, "VCB123456")
        self.assertNotContains(res_payments, "TM002")

        res_incidents = self.client.get(reverse("tenant-incidents"))
        self.assertEqual(res_incidents.status_code, 200)
        self.assertContains(res_incidents, "Hỏng đèn phòng 101")
        self.assertNotContains(res_incidents, "Rò nước phòng 202")

        res_notifs = self.client.get(reverse("tenant-notifications"))
        self.assertEqual(res_notifs.status_code, 200)
        self.assertContains(res_notifs, "Thông báo tòa 1")
        self.assertNotContains(res_notifs, "Thông báo tòa 2")

    def test_tenant_forbidden_from_operator_management_resources(self):
        self.client.force_login(self.user_a)
        for name in ("buildings", "rooms", "tenants", "contracts", "invoices", "payments", "meters", "incidents", "room-map", "room-create"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
