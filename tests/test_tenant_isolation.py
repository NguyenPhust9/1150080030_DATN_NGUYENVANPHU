from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Contract, Invoice, Payment, Room, Tenant

User = get_user_model()


class TenantIsolationTests(TestCase):
    def setUp(self):
        # 1. Quản trị viên / Chủ nhà
        self.admin = User.objects.create_user(
            username="admin_user", password="PassWord123!", role="admin"
        )
        self.building = Building.objects.create(
            name="Tòa Nhà X", address="Hồ Chí Minh", owner=self.admin
        )
        self.room_1 = Room.objects.create(
            building=self.building, number="101", floor=1, monthly_rent=Decimal("4000000")
        )
        self.room_2 = Room.objects.create(
            building=self.building, number="102", floor=1, monthly_rent=Decimal("5000000")
        )

        # 2. Khách thuê A (Tenant A)
        self.user_a = User.objects.create_user(
            username="tenant_a", password="PassWord123!", role="tenant"
        )
        self.tenant_a = Tenant.objects.create(
            user=self.user_a, full_name="Nguyễn Văn A", phone="0901000001", identity_number="111111111111"
        )
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
        self.invoice_a = Invoice.objects.create(
            code="HD001-T10",
            contract=self.contract_a,
            period=date.today().replace(day=1),
            subtotal=Decimal("4000000"),
            total_amount=Decimal("4000000"),
            paid_amount=Decimal("2000000"),
            due_date=date.today() + timedelta(days=5),
            status=Invoice.Status.PARTIALLY_PAID,
        )
        self.payment_a = Payment.objects.create(
            invoice=self.invoice_a,
            amount=Decimal("2000000"),
            paid_at=date.today(),
            method=Payment.Method.TRANSFER,
            reference="VCB123456",
            received_by=self.admin,
        )

        # 3. Khách thuê B (Tenant B)
        self.user_b = User.objects.create_user(
            username="tenant_b", password="PassWord123!", role="tenant"
        )
        self.tenant_b = Tenant.objects.create(
            user=self.user_b, full_name="Trần Thị B", phone="0902000002", identity_number="222222222222"
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
        self.invoice_b = Invoice.objects.create(
            code="HD002-T10",
            contract=self.contract_b,
            period=date.today().replace(day=1),
            subtotal=Decimal("5000000"),
            total_amount=Decimal("5000000"),
            paid_amount=Decimal("5000000"),
            due_date=date.today() + timedelta(days=5),
            status=Invoice.Status.PAID,
        )
        self.payment_b = Payment.objects.create(
            invoice=self.invoice_b,
            amount=Decimal("5000000"),
            paid_at=date.today(),
            method=Payment.Method.CASH,
            reference="TM002",
            received_by=self.admin,
        )

    def test_tenant_only_sees_own_rooms(self):
        self.client.force_login(self.user_a)
        res = self.client.get(reverse("tenant-rooms"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Phòng 101")
        self.assertNotContains(res, "Phòng 102")

    def test_tenant_only_sees_own_contracts(self):
        self.client.force_login(self.user_a)
        res = self.client.get(reverse("tenant-contracts"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "HD-001")
        self.assertNotContains(res, "HD-002")

    def test_tenant_only_sees_own_invoices(self):
        self.client.force_login(self.user_a)
        res = self.client.get(reverse("tenant-invoices"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "HD001-T10")
        self.assertNotContains(res, "HD002-T10")

    def test_tenant_cannot_access_other_tenant_invoice_detail(self):
        self.client.force_login(self.user_a)
        # Khách A xem hóa đơn của mình -> thành công
        res_own = self.client.get(reverse("tenant-invoice-detail", args=[self.invoice_a.id]))
        self.assertEqual(res_own.status_code, 200)

        # Khách A cố tình truy cập hóa đơn của Khách B qua UUID -> 404 Not Found (bị chặn)
        res_other = self.client.get(reverse("tenant-invoice-detail", args=[self.invoice_b.id]))
        self.assertEqual(res_other.status_code, 404)

    def test_tenant_only_sees_own_payments(self):
        self.client.force_login(self.user_a)
        res = self.client.get(reverse("tenant-payments"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "VCB123456")
        self.assertNotContains(res, "TM002")

    def test_tenant_redirected_to_own_views_from_management_urls(self):
        self.client.force_login(self.user_a)
        # Vào /phong/ -> chuyển hướng đến /nguoi-thue/phong/
        self.assertRedirects(self.client.get(reverse("rooms")), reverse("tenant-rooms"))
        # Vào /hop-dong/ -> chuyển hướng đến /nguoi-thue/hop-dong/
        self.assertRedirects(self.client.get(reverse("contracts")), reverse("tenant-contracts"))
        # Vào /hoa-don/ -> chuyển hướng đến /nguoi-thue/hoa-don/
        self.assertRedirects(self.client.get(reverse("invoices")), reverse("tenant-invoices"))
        # Vào /thanh-toan/ -> chuyển hướng đến /nguoi-thue/thanh-toan/
        self.assertRedirects(self.client.get(reverse("payments")), reverse("tenant-payments"))

    def test_tenant_forbidden_from_operator_only_management_resources(self):
        self.client.force_login(self.user_a)
        # Không được xem danh sách tất cả tòa nhà
        res_buildings = self.client.get(reverse("buildings"))
        self.assertEqual(res_buildings.status_code, 403)

        # Không được xem danh sách hồ sơ khách thuê khác
        res_tenants = self.client.get(reverse("tenants"))
        self.assertEqual(res_tenants.status_code, 403)

        # Không được truy cập sơ đồ phòng quản lý
        res_map = self.client.get(reverse("room-map"))
        self.assertEqual(res_map.status_code, 403)

        # Không được thêm phòng mới
        res_create_room = self.client.get(reverse("room-create"))
        self.assertEqual(res_create_room.status_code, 403)

