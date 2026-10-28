from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.rentals.models import (
    Building,
    Contract,
    ContractMember,
    ContractService,
    Invoice,
    MeterReading,
    Payment,
    Room,
    Service,
    Tenant,
)

User = get_user_model()


class BillingAndPaymentTests(TestCase):
    def setUp(self):
        self.owner1 = User.objects.create_user(username="owner_b1", password="Password123!", role="owner")
        self.owner2 = User.objects.create_user(username="owner_b2", password="Password123!", role="owner")
        self.tenant_user1 = User.objects.create_user(username="tenant_b1", password="Password123!", role="tenant")
        self.tenant_user2 = User.objects.create_user(username="tenant_b2", password="Password123!", role="tenant")

        self.b1 = Building.objects.create(name="Tòa Alpha", address="123 Nguyễn Trãi", owner=self.owner1)
        self.b2 = Building.objects.create(name="Tòa Beta", address="456 Lê Lợi", owner=self.owner2)

        self.room1 = Room.objects.create(
            building=self.b1, number="101", floor=1, monthly_rent=Decimal("3000000"), max_occupants=4, status=Room.Status.OCCUPIED
        )
        self.room1_b = Room.objects.create(
            building=self.b1, number="102", floor=1, monthly_rent=Decimal("3200000"), max_occupants=4, status=Room.Status.OCCUPIED
        )
        self.room2 = Room.objects.create(
            building=self.b2, number="201", floor=2, monthly_rent=Decimal("4000000"), max_occupants=4, status=Room.Status.OCCUPIED
        )

        self.tenant1 = Tenant.objects.create(
            owner=self.owner1, user=self.tenant_user1, full_name="Khách 1", phone="0901000111", identity_number="CCCD101"
        )
        self.tenant1_mate = Tenant.objects.create(
            owner=self.owner1, full_name="Bạn cùng phòng 1", phone="0901000112", identity_number="CCCD102"
        )
        self.tenant1_b = Tenant.objects.create(
            owner=self.owner1, full_name="Khách 1B", phone="0901000113", identity_number="CCCD103"
        )
        self.tenant2 = Tenant.objects.create(
            owner=self.owner2, user=self.tenant_user2, full_name="Khách 2", phone="0902000222", identity_number="CCCD201"
        )

        self.contract1 = Contract.objects.create(
            code="HD-B1-101",
            room=self.room1,
            representative=self.tenant1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            monthly_rent=Decimal("3000000"),
            deposit_amount=Decimal("3000000"),
            status=Contract.Status.ACTIVE,
        )
        ContractMember.objects.create(
            contract=self.contract1, tenant=self.tenant1_mate, joined_date=date(2026, 1, 1)
        )
        self.contract1_b = Contract.objects.create(
            code="HD-B1-102",
            room=self.room1_b,
            representative=self.tenant1_b,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            monthly_rent=Decimal("3200000"),
            deposit_amount=Decimal("3200000"),
            status=Contract.Status.ACTIVE,
        )
        self.contract2 = Contract.objects.create(
            code="HD-B2-201",
            room=self.room2,
            representative=self.tenant2,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            monthly_rent=Decimal("4000000"),
            deposit_amount=Decimal("4000000"),
            status=Contract.Status.ACTIVE,
        )

        # Services
        self.srv_elec = Service.objects.create(
            owner=self.owner1, name="Điện sinh hoạt", unit=Service.Unit.KWH, unit_price=Decimal("3500"), is_metered=True
        )
        self.srv_water = Service.objects.create(
            owner=self.owner1, name="Nước thủy cục", unit=Service.Unit.CUBIC_METER, unit_price=Decimal("18000"), is_metered=True
        )
        self.srv_trash = Service.objects.create(
            owner=self.owner1, name="Rác & Vệ sinh", unit=Service.Unit.PERSON, unit_price=Decimal("50000")
        )
        self.srv_wifi = Service.objects.create(
            owner=self.owner1, name="Internet Wifi", unit=Service.Unit.ROOM, unit_price=Decimal("100000")
        )
        self.srv_parking = Service.objects.create(
            owner=self.owner1, name="Giữ xe cố định", unit=Service.Unit.FIXED, unit_price=Decimal("150000")
        )

    def test_service_crud_and_contract_service_attachment(self):
        self.client.force_login(self.owner1)

        # Create a new service via view
        res = self.client.post(
            reverse("service-create"),
            {
                "name": "Phí quản lý",
                "unit": Service.Unit.FIXED,
                "unit_price": "80000",
                "is_active": "on",
            },
        )
        self.assertEqual(res.status_code, 302)
        mgmt_srv = Service.objects.get(name="Phí quản lý", owner=self.owner1)
        self.assertEqual(mgmt_srv.unit_price, Decimal("80000"))

        # Update service price
        res = self.client.post(
            reverse("service-update", args=[mgmt_srv.id]),
            {
                "name": "Phí quản lý",
                "unit": Service.Unit.FIXED,
                "unit_price": "90000",
                "is_active": "on",
            },
        )
        self.assertEqual(res.status_code, 302)
        mgmt_srv.refresh_from_db()
        self.assertEqual(mgmt_srv.unit_price, Decimal("90000"))

        # Attach services to contract1
        res = self.client.post(
            reverse("contract-service-add", args=[self.contract1.id]),
            {
                "service": str(self.srv_trash.id),
                "unit_price": "50000",
                "quantity": "1",
                "is_active": "on",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertTrue(
            ContractService.objects.filter(contract=self.contract1, service=self.srv_trash).exists()
        )

    def test_meter_reading_auto_previous_value_and_validations(self):
        self.client.force_login(self.owner1)

        # Period 1: 2026-01-01 (initial reading 100 -> 150)
        res = self.client.post(
            reverse("meter-create"),
            {
                "room": str(self.room1.id),
                "meter_type": MeterReading.MeterType.ELECTRICITY,
                "period": "2026-01-01",
                "previous_value": "100",
                "current_value": "150",
            },
        )
        self.assertEqual(res.status_code, 302)
        m1 = MeterReading.objects.get(room=self.room1, meter_type="electricity", period=date(2026, 1, 1))
        self.assertEqual(m1.consumption, Decimal("50"))

        # Period 2: 2026-02-01 with blank previous_value -> should auto-take 150 from Period 1!
        res = self.client.post(
            reverse("meter-create"),
            {
                "room": str(self.room1.id),
                "meter_type": MeterReading.MeterType.ELECTRICITY,
                "period": "2026-02-01",
                "previous_value": "",
                "current_value": "210",
            },
        )
        self.assertEqual(res.status_code, 302)
        m2 = MeterReading.objects.get(room=self.room1, meter_type="electricity", period=date(2026, 2, 1))
        self.assertEqual(m2.previous_value, Decimal("150"))
        self.assertEqual(m2.consumption, Decimal("60"))

        # Block current_value < previous_value
        res = self.client.post(
            reverse("meter-create"),
            {
                "room": str(self.room1.id),
                "meter_type": MeterReading.MeterType.ELECTRICITY,
                "period": "2026-03-01",
                "previous_value": "",
                "current_value": "180",  # < 210
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(
            MeterReading.objects.filter(room=self.room1, meter_type="electricity", period=date(2026, 3, 1)).exists()
        )

        # Block duplicate (room, meter_type, period)
        res = self.client.post(
            reverse("meter-create"),
            {
                "room": str(self.room1.id),
                "meter_type": MeterReading.MeterType.ELECTRICITY,
                "period": "2026-02-01",
                "previous_value": "150",
                "current_value": "220",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            MeterReading.objects.filter(room=self.room1, meter_type="electricity", period=date(2026, 2, 1)).count(),
            1,
        )

        # Block selecting room belonging to owner2
        res = self.client.post(
            reverse("meter-create"),
            {
                "room": str(self.room2.id),
                "meter_type": MeterReading.MeterType.ELECTRICITY,
                "period": "2026-02-01",
                "previous_value": "0",
                "current_value": "50",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(MeterReading.objects.filter(room=self.room2).exists())

    def test_invoice_calculation_price_snapshot_duplicate_check_and_lifecycle(self):
        self.client.force_login(self.owner1)

        # Attach services to contract1
        ContractService.objects.create(
            contract=self.contract1, service=self.srv_elec, unit_price=Decimal("3500"), quantity=Decimal("1")
        )
        ContractService.objects.create(
            contract=self.contract1, service=self.srv_water, unit_price=Decimal("18000"), quantity=Decimal("1")
        )
        # Per-person service (contract1 has 1 representative + 1 member = 2 people)
        ContractService.objects.create(
            contract=self.contract1, service=self.srv_trash, unit_price=Decimal("50000"), quantity=Decimal("1")
        )
        # Per-room service
        ContractService.objects.create(
            contract=self.contract1, service=self.srv_wifi, unit_price=Decimal("100000"), quantity=Decimal("1")
        )
        # Fixed service
        ContractService.objects.create(
            contract=self.contract1, service=self.srv_parking, unit_price=Decimal("150000"), quantity=Decimal("1")
        )

        # Record meter readings for 2026-04-01:
        # Electricity: 100 -> 200 = 100 kWh * 3,500 = 350,000
        # Water: 20 -> 30 = 10 m3 * 18,000 = 180,000
        MeterReading.objects.create(
            room=self.room1,
            meter_type=MeterReading.MeterType.ELECTRICITY,
            period=date(2026, 4, 1),
            previous_value=Decimal("100"),
            current_value=Decimal("200"),
            recorded_by=self.owner1,
        )
        MeterReading.objects.create(
            room=self.room1,
            meter_type=MeterReading.MeterType.WATER,
            period=date(2026, 4, 1),
            previous_value=Decimal("20"),
            current_value=Decimal("30"),
            recorded_by=self.owner1,
        )

        # Create draft invoice via view with surcharge=50,000 and discount=30,000
        # Expected subtotal:
        # Rent: 3,000,000
        # Elec: 350,000
        # Water: 180,000
        # Trash (2 persons * 50,000): 100,000
        # Wifi (1 room * 100,000): 100,000
        # Parking (fixed): 150,000
        # Surcharge: 50,000
        # Subtotal = 3,930,000; Discount = 30,000; Total = 3,900,000
        due = date.today() + timedelta(days=10)
        res = self.client.post(
            reverse("invoice-create"),
            {
                "contract": str(self.contract1.id),
                "period": "2026-04-01",
                "due_date": due.isoformat(),
                "surcharge": "50000",
                "surcharge_description": "Phụ thu sửa khóa",
                "discount": "30000",
                "status": Invoice.Status.DRAFT,
                "notes": "Hóa đơn tháng 4",
            },
        )
        self.assertEqual(res.status_code, 302)
        invoice = Invoice.objects.get(contract=self.contract1, period=date(2026, 4, 1))
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertEqual(invoice.subtotal, Decimal("3930000"))
        self.assertEqual(invoice.discount, Decimal("30000"))
        self.assertEqual(invoice.total_amount, Decimal("3900000"))
        self.assertEqual(invoice.balance, Decimal("3900000"))

        # Block duplicate invoice for same contract and period
        res_dup = self.client.post(
            reverse("invoice-create"),
            {
                "contract": str(self.contract1.id),
                "period": "2026-04-01",
                "due_date": due.isoformat(),
                "surcharge": "0",
                "surcharge_description": "",
                "discount": "0",
                "status": Invoice.Status.DRAFT,
                "notes": "",
            },
        )
        self.assertEqual(res_dup.status_code, 200)
        self.assertEqual(
            Invoice.objects.filter(contract=self.contract1, period=date(2026, 4, 1)).count(), 1
        )

        # Changing service price later MUST NOT change existing invoice items or total
        self.srv_elec.unit_price = Decimal("5000")
        self.srv_elec.save()
        ContractService.objects.filter(contract=self.contract1, service=self.srv_elec).update(
            unit_price=Decimal("5000")
        )
        invoice.refresh_from_db()
        elec_item = invoice.items.filter(service=self.srv_elec).first()
        self.assertEqual(elec_item.unit_price, Decimal("3500"))
        self.assertEqual(elec_item.amount, Decimal("350000"))
        self.assertEqual(invoice.total_amount, Decimal("3900000"))

        # Edit draft invoice discount (30,000 -> 80,000 => total becomes 3,850,000)
        res = self.client.post(
            reverse("invoice-update", args=[invoice.id]),
            {
                "due_date": due.isoformat(),
                "discount": "80000",
                "notes": "Giảm trừ thêm 50k",
            },
        )
        self.assertEqual(res.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, Decimal("3850000"))

        # Issue invoice -> status becomes ISSUED and tenant receives notification
        res = self.client.post(reverse("invoice-issue", args=[invoice.id]))
        self.assertEqual(res.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
        self.assertTrue(self.tenant_user1.notifications.filter(title__icontains=invoice.code).exists())

        # Editing non-draft invoice is blocked
        res = self.client.post(
            reverse("invoice-update", args=[invoice.id]),
            {"due_date": due.isoformat(), "discount": "500000", "notes": "Hack"},
        )
        self.assertEqual(res.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.discount, Decimal("80000"))

    def test_bulk_invoice_generation_and_cancel_invoice_with_reason(self):
        self.client.force_login(self.owner1)
        due = date.today() + timedelta(days=7)

        # Bulk generate for 2026-05-01 across owner1's active contracts (contract1 and contract1_b)
        res = self.client.post(
            reverse("invoice-bulk-create"),
            {
                "building": "",
                "period": "2026-05-01",
                "due_date": due.isoformat(),
                "status": Invoice.Status.DRAFT,
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Invoice.objects.filter(contract=self.contract1, period=date(2026, 5, 1)).exists())
        self.assertTrue(Invoice.objects.filter(contract=self.contract1_b, period=date(2026, 5, 1)).exists())
        self.assertFalse(Invoice.objects.filter(contract=self.contract2, period=date(2026, 5, 1)).exists())

        inv = Invoice.objects.get(contract=self.contract1, period=date(2026, 5, 1))
        # Cancel invoice with reason
        res = self.client.post(
            reverse("invoice-cancel", args=[inv.id]),
            {"reason": "Nhập sai kỳ thanh toán"},
        )
        self.assertEqual(res.status_code, 302)
        inv.refresh_from_db()
        self.assertEqual(inv.status, Invoice.Status.CANCELLED)
        self.assertIn("Nhập sai kỳ thanh toán", inv.notes)

    def test_payments_partial_full_overpayment_draft_cancelled_and_void(self):
        self.client.force_login(self.owner1)
        due = date.today() + timedelta(days=5)

        # Create a DRAFT invoice first
        res = self.client.post(
            reverse("invoice-create"),
            {
                "contract": str(self.contract1.id),
                "period": "2026-06-01",
                "due_date": due.isoformat(),
                "surcharge": "0",
                "surcharge_description": "",
                "discount": "0",
                "status": Invoice.Status.DRAFT,
                "notes": "",
            },
        )
        invoice = Invoice.objects.get(contract=self.contract1, period=date(2026, 6, 1))
        now_str = timezone.now().strftime("%Y-%m-%dT%H:%M")

        # 1. Paying a DRAFT invoice is blocked
        res = self.client.post(
            reverse("payment-create"),
            {
                "invoice": str(invoice.id),
                "amount": "1000000",
                "paid_at": now_str,
                "method": Payment.Method.CASH,
                "reference": "REF-DRAFT",
                "notes": "",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(invoice.payments.count(), 0)

        # Issue the invoice (total = 3,000,000)
        self.client.post(reverse("invoice-issue", args=[invoice.id]))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)

        # 2. Partial payment (1,200,000) -> status becomes PARTIAL, balance = 1,800,000
        res = self.client.post(
            reverse("payment-create"),
            {
                "invoice": str(invoice.id),
                "amount": "1200000",
                "paid_at": now_str,
                "method": Payment.Method.TRANSFER,
                "reference": "TXN-001",
                "notes": "Thanh toán đợt 1",
            },
        )
        self.assertEqual(res.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("1200000"))
        self.assertEqual(invoice.balance, Decimal("1800000"))
        self.assertEqual(invoice.status, Invoice.Status.PARTIAL)

        # 3. Overpayment (2,000,000 > balance 1,800,000) is blocked
        res = self.client.post(
            reverse("payment-create"),
            {
                "invoice": str(invoice.id),
                "amount": "2000000",
                "paid_at": now_str,
                "method": Payment.Method.TRANSFER,
                "reference": "TXN-OVER",
                "notes": "",
            },
        )
        self.assertEqual(res.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("1200000"))

        # 4. Remaining full payment (1,800,000) -> status becomes PAID, balance = 0
        res = self.client.post(
            reverse("payment-create"),
            {
                "invoice": str(invoice.id),
                "amount": "1800000",
                "paid_at": now_str,
                "method": Payment.Method.CASH,
                "reference": "TXN-002",
                "notes": "Tất toán",
            },
        )
        self.assertEqual(res.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("3000000"))
        self.assertEqual(invoice.balance, Decimal("0"))
        self.assertEqual(invoice.status, Invoice.Status.PAID)

        # 5. Paying an already PAID invoice is blocked
        res = self.client.post(
            reverse("payment-create"),
            {
                "invoice": str(invoice.id),
                "amount": "100000",
                "paid_at": now_str,
                "method": Payment.Method.CASH,
                "reference": "TXN-EXTRA",
                "notes": "",
            },
        )
        self.assertEqual(res.status_code, 200)

        # 6. Void second payment (1,800,000) -> soft void (not deleted), invoice reverts to PARTIAL with balance 1,800,000
        second_payment = invoice.payments.get(reference="TXN-002")
        res = self.client.post(
            reverse("payment-void", args=[second_payment.id]),
            {"reason": "Nhập nhầm số tiền"},
        )
        self.assertEqual(res.status_code, 302)
        second_payment.refresh_from_db()
        invoice.refresh_from_db()
        self.assertTrue(second_payment.is_void)
        self.assertTrue(Payment.objects.filter(pk=second_payment.id).exists())
        self.assertEqual(invoice.paid_amount, Decimal("1200000"))
        self.assertEqual(invoice.balance, Decimal("1800000"))
        self.assertEqual(invoice.status, Invoice.Status.PARTIAL)

        # Void first payment too -> invoice reverts to ISSUED with paid_amount = 0
        first_payment = invoice.payments.get(reference="TXN-001")
        self.client.post(reverse("payment-void", args=[first_payment.id]), {"reason": "Hủy hết"})
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("0"))
        self.assertEqual(invoice.balance, Decimal("3000000"))
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
