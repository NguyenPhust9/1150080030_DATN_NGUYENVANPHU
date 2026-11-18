import io
import json
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from apps.rentals.models import (
    Building, Contract, ContractService, Invoice, InvoiceItem, MeterReading,
    Notification, Payment, Room, Service, Tenant,
)


class RentalBillingBackfillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user("billing-owner", role="owner")
        cls.building = Building.objects.create(name="Billing building", address="Test", owner=cls.owner)
        cls.contracts = []
        for index in range(2):
            room = Room.objects.create(building=cls.building, number=f"A10{index + 1}", floor=1,
                                       monthly_rent=3000000 + index * 500000, deposit_amount=3000000,
                                       status=Room.Status.OCCUPIED)
            tenant = Tenant.objects.create(owner=cls.owner, full_name=f"Tenant {index}")
            cls.contracts.append(Contract.objects.create(
                code="HD-MAU-20261118-TEST" if index == 0 else "HD-2026-EXISTING",
                room=room, representative=tenant,
                start_date=date(2026, 11, 18) if index == 0 else date(2026, 6, 1),
                end_date=date(2027, 11, 18) if index == 0 else date(2027, 6, 1),
                monthly_rent=room.monthly_rent, deposit_amount=room.deposit_amount,
                status=Contract.Status.ACTIVE,
                notes="Hợp đồng mẫu được phân bổ ngẫu nhiên." if index == 0 else "Giữ nguyên ghi chú cũ.",
            ))
        cls.allocated, cls.existing = cls.contracts

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.backup_dir = Path(self.directory.name) / "backups"
        self.source_path = Path(self.directory.name) / "allocation.json"
        self.source = {
            "state": "committed",
            "plan": {"owner_id": str(self.owner.pk), "start_date": "2026-11-18", "end_date": "2027-11-18"},
            "new_contracts": [{
                "id": str(self.allocated.pk), "room_id": str(self.allocated.room_id),
                "representative_id": str(self.allocated.representative_id),
                "monthly_rent": str(self.allocated.monthly_rent),
                "deposit_amount": str(self.allocated.deposit_amount),
            }],
        }
        self.write_source()

    def write_source(self):
        self.source_path.write_text(json.dumps(self.source), encoding="utf-8")

    def run_command(self, **overrides):
        output = io.StringIO()
        options = dict(
            owner_id=self.owner.pk, allocation_backup=self.source_path,
            periods=[date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)],
            contract_start_date=date(2026, 9, 1), contract_end_date=date(2027, 9, 1),
            paid_through=date(2026, 11, 1), backup_dir=self.backup_dir,
            stdout=output, verbosity=0,
        )
        options.update(overrides)
        call_command("backfill_rental_billing", **options)
        return json.loads(output.getvalue().strip().splitlines()[-1])

    def make_invoice(self, *, contract=None, period=date(2026, 9, 1), status=Invoice.Status.ISSUED,
                     total=Decimal("3500000"), paid=Decimal("0")):
        return Invoice.objects.create(
            code=f"INV-{uuid.uuid4().hex[:12]}", contract=contract or self.existing, period=period,
            issued_date=period, due_date=period.replace(day=5), subtotal=total,
            total_amount=total, paid_amount=paid, status=status,
        )

    def test_dry_run_plans_three_months_without_writing(self):
        contracts_before = list(Contract.objects.order_by("pk").values())
        report = self.run_command()
        self.assertFalse(report["applied"])
        self.assertEqual(report["new_invoices"], 6)
        self.assertEqual(report["new_payments"], 6)
        self.assertEqual(report["updated_contracts"], 1)
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(list(Contract.objects.order_by("pk").values()), contracts_before)
        self.assertFalse(self.backup_dir.exists())

    def test_apply_sets_rent_totals_and_payments_for_all_three_months(self):
        existing_before = Contract.objects.filter(pk=self.existing.pk).values().get()
        report = self.run_command(apply=True)
        self.assertTrue(report["applied"])
        self.assertEqual(Invoice.objects.count(), 6)
        self.assertEqual(Payment.objects.count(), 6)
        self.assertEqual(InvoiceItem.objects.count(), 6)
        self.assertEqual(Invoice.objects.aggregate(total=Sum("total_amount"))["total"], Decimal("19500000"))
        self.allocated.refresh_from_db()
        self.assertEqual(self.allocated.code, "HD-20261118-TEST")
        self.assertEqual(self.allocated.notes, "")
        self.assertEqual(self.allocated.start_date, date(2026, 9, 1))
        self.assertEqual(self.allocated.end_date, date(2027, 9, 1))
        self.assertEqual(Contract.objects.filter(pk=self.existing.pk).values().get(), existing_before)
        for invoice in Invoice.objects.select_related("contract"):
            self.assertEqual(invoice.status, Invoice.Status.PAID)
            self.assertEqual(invoice.total_amount, invoice.contract.monthly_rent)
            self.assertEqual(invoice.paid_amount, invoice.total_amount)
            self.assertEqual(invoice.items.get().amount, invoice.total_amount)
            payment = invoice.payments.get()
            self.assertEqual(payment.amount, invoice.total_amount)
            self.assertEqual(payment.method, Payment.Method.OTHER)
            self.assertEqual(payment.received_by_id, self.owner.pk)
            self.assertTrue(payment.reference)
            self.assertGreaterEqual(timezone.localdate(payment.paid_at), invoice.issued_date)
            self.assertGreaterEqual(timezone.localdate(payment.paid_at), invoice.due_date)
            for text in (invoice.code, invoice.notes, invoice.items.get().description, payment.reference, payment.notes):
                self.assertNotIn("mẫu", text.lower())
                self.assertNotIn("mau", text.lower())
        self.assertFalse(Notification.objects.exists())
        snapshot = json.loads(Path(report["backup"]).read_text(encoding="utf-8"))
        self.assertEqual(snapshot["state"], "committed")

    def test_existing_partial_invoice_gets_only_balance_and_preserves_history(self):
        invoice = self.make_invoice(status=Invoice.Status.PARTIAL, total=Decimal("3750000"), paid=Decimal("1000000"))
        invoice.issued_date = date(2026, 9, 8)
        invoice.due_date = date(2026, 9, 15)
        invoice.save()
        InvoiceItem.objects.create(invoice=invoice, description="Rent and agreed charges", quantity=1,
                                   unit_price=Decimal("3750000"), amount=Decimal("3750000"))
        payment = Payment.objects.create(invoice=invoice, amount=Decimal("1000000"),
                                         paid_at=timezone.make_aware(datetime(2026, 9, 22, 15)),
                                         method=Payment.Method.CASH, received_by=self.owner, reference="KEEP-ORIGINAL")
        original_payment = Payment.objects.filter(pk=payment.pk).values().get()
        original_items = list(invoice.items.order_by("pk").values())
        report = self.run_command(apply=True)
        self.assertEqual(report["new_invoices"], 5)
        self.assertEqual(report["new_payments"], 6)
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("3750000"))
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.total_amount, Decimal("3750000"))
        self.assertEqual(Payment.objects.filter(pk=payment.pk).values().get(), original_payment)
        self.assertEqual(list(invoice.items.order_by("pk").values()), original_items)
        top_up = invoice.payments.exclude(pk=payment.pk).get()
        self.assertEqual(top_up.amount, Decimal("2750000"))
        self.assertGreaterEqual(top_up.paid_at, payment.paid_at)

    def test_cancelled_invoice_is_kept_and_replaced(self):
        cancelled = self.make_invoice(status=Invoice.Status.CANCELLED)
        before = Invoice.objects.filter(pk=cancelled.pk).values().get()
        self.run_command(apply=True)
        self.assertEqual(Invoice.objects.filter(pk=cancelled.pk).values().get(), before)
        self.assertEqual(Invoice.objects.filter(contract=self.existing, period=date(2026, 9, 1)).count(), 2)
        self.assertFalse(cancelled.payments.exists())
        self.assertEqual(Invoice.objects.filter(status=Invoice.Status.PAID).count(), 6)

    def test_paid_through_october_leaves_november_unpaid(self):
        report = self.run_command(apply=True, paid_through=date(2026, 10, 1))
        self.assertEqual(report["new_invoices"], 6)
        self.assertEqual(report["new_payments"], 4)
        november = Invoice.objects.filter(period=date(2026, 11, 1))
        self.assertEqual(november.count(), 2)
        self.assertFalse(november.filter(status=Invoice.Status.PAID).exists())
        self.assertTrue(all(invoice.paid_amount == 0 for invoice in november))
        self.assertFalse(Payment.objects.filter(invoice__period=date(2026, 11, 1)).exists())

    def test_second_apply_is_idempotent(self):
        self.run_command(apply=True)
        before = {model: list(model.objects.order_by("pk").values())
                  for model in (Contract, Invoice, InvoiceItem, Payment)}
        backup_count = len(list(self.backup_dir.glob("*.json")))
        report = self.run_command(apply=True)
        for field in ("new_invoices", "new_payments", "updated_contracts", "updated_invoices"):
            self.assertEqual(report[field], 0)
        for model, records in before.items():
            self.assertEqual(list(model.objects.order_by("pk").values()), records)
        self.assertEqual(len(list(self.backup_dir.glob("*.json"))), backup_count)

    def test_other_owner_and_earlier_invoices_are_unchanged(self):
        other = get_user_model().objects.create_user("other-billing-owner", role="owner")
        building = Building.objects.create(owner=other, name="Other building", address="Test")
        room = Room.objects.create(building=building, number="Z101", monthly_rent=2500000)
        tenant = Tenant.objects.create(owner=other, full_name="Other tenant")
        contract = Contract.objects.create(code="HD-MAU-OTHER", room=room, representative=tenant,
                                           start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
                                           monthly_rent=2500000, status=Contract.Status.ACTIVE, notes="Keep this.")
        old_invoice = self.make_invoice(period=date(2026, 8, 1))
        other_invoice = self.make_invoice(contract=contract)
        records = list(Invoice.objects.order_by("pk").values())
        contract_before = Contract.objects.filter(pk=contract.pk).values().get()
        self.run_command(apply=True)
        self.assertEqual(Contract.objects.filter(pk=contract.pk).values().get(), contract_before)
        self.assertEqual(list(Invoice.objects.filter(pk__in=[old_invoice.pk, other_invoice.pk]).order_by("pk").values()), records)
        self.assertFalse(Payment.objects.filter(invoice_id__in=[old_invoice.pk, other_invoice.pk]).exists())

    def test_existing_contract_dates_limit_billable_periods(self):
        self.existing.start_date = date(2026, 10, 1)
        self.existing.save()
        report = self.run_command(apply=True)
        self.assertEqual(report["new_invoices"], 5)
        self.assertEqual(list(self.existing.invoices.order_by("period").values_list("period", flat=True)),
                         [date(2026, 10, 1), date(2026, 11, 1)])

    def test_uncommitted_or_wrong_owner_source_is_rejected(self):
        for change in ({"state": "prepared"}, {"plan": {**self.source["plan"], "owner_id": str(uuid.uuid4())}}):
            with self.subTest(change=change):
                changed = {**self.source, **change}
                self.source_path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaisesRegex(CommandError, "snapshot must be committed and belong to this owner"):
                    self.run_command(apply=True)
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(Payment.objects.exists())

    def test_source_contract_mismatch_is_rejected(self):
        self.source["new_contracts"][0]["room_id"] = str(self.existing.room_id)
        self.write_source()
        with self.assertRaisesRegex(CommandError, "allocated contract changed"):
            self.run_command(apply=True)
        self.assertFalse(Invoice.objects.exists())

    def test_attached_service_prevents_incomplete_rent_only_invoice(self):
        service = Service.objects.create(owner=self.owner, name="Internet", unit=Service.Unit.FIXED, unit_price=100000)
        ContractService.objects.create(contract=self.existing, service=service, unit_price=100000)
        with self.assertRaisesRegex(CommandError, "missing invoice has services or meter readings"):
            self.run_command(apply=True)
        self.assertFalse(Invoice.objects.exists())

    def test_meter_reading_prevents_incomplete_rent_only_invoice(self):
        MeterReading.objects.create(room=self.existing.room, meter_type=MeterReading.MeterType.ELECTRICITY,
                                    period=date(2026, 9, 1), previous_value=100, current_value=150, recorded_by=self.owner)
        with self.assertRaisesRegex(CommandError, "missing invoice has services or meter readings"):
            self.run_command(apply=True)
        self.assertFalse(Invoice.objects.exists())

    def test_failure_after_batch_writes_rolls_back_every_change(self):
        from apps.rentals.management.commands.backfill_rental_billing import apply_backfill

        before = list(Contract.objects.order_by("pk").values())

        def fail_after_writes(plan):
            apply_backfill(plan)
            self.assertEqual(Invoice.objects.count(), 6)
            self.assertEqual(Payment.objects.count(), 6)
            self.assertEqual(Contract.objects.get(pk=self.allocated.pk).start_date, date(2026, 9, 1))
            raise RuntimeError("Simulated backfill failure")

        with patch("apps.rentals.management.commands.backfill_rental_billing.apply_backfill", side_effect=fail_after_writes):
            with self.assertRaisesRegex(RuntimeError, "Simulated backfill failure"):
                self.run_command(apply=True)
        self.assertEqual(list(Contract.objects.order_by("pk").values()), before)
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(InvoiceItem.objects.exists())
        self.assertFalse(Payment.objects.exists())
        snapshot = json.loads(next(self.backup_dir.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(snapshot["state"], "prepared")
