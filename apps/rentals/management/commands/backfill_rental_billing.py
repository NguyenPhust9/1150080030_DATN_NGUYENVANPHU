"""Backfill explicitly requested rental periods without resetting existing data."""
import json
import uuid
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.rentals.models import (
    Contract, ContractService, Invoice, InvoiceItem, MeterReading, Payment,
)


def month(value):
    value = str(value)
    parsed = date.fromisoformat(f"{value}-01" if len(value) == 7 else value)
    if parsed.day != 1:
        raise ValueError("Billing periods must start on the first day of a month.")
    return parsed


def prepare_backfill(owner_id, allocation_backup, periods, contract_start_date,
                     contract_end_date, paid_through, lock=False):
    source = json.loads(Path(allocation_backup).read_text(encoding="utf-8"))
    if source.get("state") != "committed" or source["plan"]["owner_id"] != str(owner_id):
        raise CommandError("Allocation snapshot must be committed and belong to this owner.")
    periods = sorted(set(periods))
    if not periods or any(period.day != 1 for period in periods) or paid_through.day != 1:
        raise CommandError("Billing periods must be the first day of each month.")
    if contract_start_date >= contract_end_date:
        raise CommandError("Contract end date must be after its start date.")
    if periods[-1] > timezone.localdate().replace(day=1):
        raise CommandError("Cannot backfill a future billing period.")
    contracts_query = Contract.objects.filter(room__building__owner_id=owner_id).order_by("pk")
    if lock:
        contracts_query = contracts_query.select_for_update()
    contracts = list(contracts_query)
    contracts_by_id = {str(contract.pk): contract for contract in contracts}
    source_ids = [record["id"] for record in source["new_contracts"]]
    if len(set(source_ids)) != len(source_ids) or not set(source_ids).issubset(contracts_by_id):
        raise CommandError("Allocation contains duplicate, missing or out-of-scope contracts.")
    before = {"contracts": list(contracts_query.values())}
    original_dates = (date.fromisoformat(source["plan"]["start_date"]),
                      date.fromisoformat(source["plan"]["end_date"]))
    requested_dates = (contract_start_date, contract_end_date)
    contracts_changed = []
    for record in source["new_contracts"]:
        contract = contracts_by_id[record["id"]]
        if (contract.status != Contract.Status.ACTIVE
                or str(contract.room_id) != record["room_id"]
                or str(contract.representative_id) != record["representative_id"]
                or contract.monthly_rent != Decimal(record["monthly_rent"])
                or contract.deposit_amount != Decimal(record["deposit_amount"])
                or (contract.start_date, contract.end_date) not in (original_dates, requested_dates)):
            raise CommandError("An allocated contract changed since the snapshot; review before updating.")
        new_code = contract.code.replace("HD-MAU-", "HD-", 1) if contract.code.startswith("HD-MAU-") else contract.code
        new_notes = "" if contract.notes.startswith("Hợp đồng mẫu") else contract.notes
        if (contract.code, contract.notes, contract.start_date, contract.end_date) != (
            new_code, new_notes, contract_start_date, contract_end_date
        ):
            contract.code, contract.notes = new_code, new_notes
            contract.start_date, contract.end_date = requested_dates
            contract.updated_at = timezone.now()
            contracts_changed.append(contract)
    if len({contract.code for contract in contracts}) != len(contracts):
        raise CommandError("Renaming would create duplicate contract codes.")

    invoices_query = Invoice.objects.filter(contract__in=contracts).order_by("pk")
    if lock:
        invoices_query = invoices_query.select_for_update()
    invoices = list(invoices_query)
    items = list(InvoiceItem.objects.filter(invoice__in=invoices).order_by("pk").values())
    payments = list(Payment.objects.filter(invoice__in=invoices).order_by("pk").values())
    before.update(invoices=list(invoices_query.values()), items=items, payments=payments)
    by_period = {(invoice.contract_id, invoice.period): invoice for invoice in invoices
                 if invoice.status != Invoice.Status.CANCELLED}
    item_totals, paid_totals = defaultdict(Decimal), defaultdict(Decimal)
    latest_paid = {}
    for item in items:
        item_totals[item["invoice_id"]] += item["amount"]
    for payment in payments:
        if not payment["is_void"]:
            invoice_id = payment["invoice_id"]
            paid_totals[invoice_id] += payment["amount"]
            latest_paid[invoice_id] = max(latest_paid.get(invoice_id, payment["paid_at"]), payment["paid_at"])

    targets, new_invoices, new_items, new_payments, invoices_changed = [], [], [], [], []
    used_codes = set(Invoice.objects.values_list("code", flat=True))
    missing_pairs = []
    for contract in contracts:
        if contract.status != Contract.Status.ACTIVE:
            continue
        for period in periods:
            # Backfill full monthly rent only for contracts covering the period.
            if contract.start_date > period or contract.end_date < period:
                continue
            invoice = by_period.get((contract.id, period))
            if invoice is None:
                base_code = f"HD-{period:%Y%m}-{str(contract.id)[:8].upper()}"
                code, suffix = base_code, 2
                while code in used_codes:
                    code, suffix = f"{base_code}-{suffix}", suffix + 1
                used_codes.add(code)
                invoice = Invoice(
                    code=code, contract_id=contract.id, period=period,
                    issued_date=period.replace(day=contract.billing_day),
                    due_date=period.replace(day=max(contract.billing_day, contract.due_day)),
                    subtotal=contract.monthly_rent, total_amount=contract.monthly_rent,
                    status=Invoice.Status.ISSUED,
                )
                new_invoices.append(invoice)
                new_items.append(InvoiceItem(
                    invoice_id=invoice.id, description=f"Tiền phòng tháng {period:%m/%Y}",
                    quantity=Decimal("1"), unit_price=contract.monthly_rent, amount=contract.monthly_rent,
                ))
                missing_pairs.append((contract.id, contract.room_id, period))
            else:
                if (invoice.subtotal != item_totals[invoice.id]
                        or invoice.total_amount != max(item_totals[invoice.id] - invoice.discount, Decimal("0"))
                        or invoice.paid_amount != paid_totals[invoice.id]
                        or invoice.paid_amount > invoice.total_amount):
                    raise CommandError(f"Invoice {invoice.code} has inconsistent totals; review before backfilling.")
            targets.append(invoice)
            if period <= paid_through and invoice.balance > 0:
                payment_day = max(invoice.issued_date, invoice.due_date)
                paid_at = timezone.make_aware(datetime.combine(payment_day, time(9)))
                if invoice.id in latest_paid:
                    paid_at = max(paid_at, latest_paid[invoice.id])
                if paid_at > timezone.now():
                    raise CommandError("Cannot record a payment in the future.")
                new_payments.append(Payment(
                    invoice_id=invoice.id, amount=invoice.balance, paid_at=paid_at,
                    method=Payment.Method.OTHER, received_by_id=owner_id,
                    reference=f"TT-{period:%Y%m}-{invoice.id.hex[:10].upper()}",
                ))
                invoice.paid_amount = invoice.total_amount
                invoice.status = Invoice.Status.PAID
                if invoice not in new_invoices:
                    invoice.updated_at = timezone.now()
                    invoices_changed.append(invoice)
            elif invoice in new_invoices and invoice.due_date < timezone.localdate():
                invoice.status = Invoice.Status.OVERDUE

    # This command fills rent-only gaps. Leave bills requiring additional fees
    # to the regular billing service instead of silently omitting known charges.
    service_contracts = set(ContractService.objects.filter(
        contract_id__in=[row[0] for row in missing_pairs], is_active=True, service__is_active=True,
    ).values_list("contract_id", flat=True))
    reading_pairs = set(MeterReading.objects.filter(
        room_id__in=[row[1] for row in missing_pairs], period__in=periods,
    ).values_list("room_id", "period"))
    if any(contract_id in service_contracts or (room_id, period) in reading_pairs
           for contract_id, room_id, period in missing_pairs):
        raise CommandError("A missing invoice has services or meter readings; use the full billing workflow for it.")
    for obj in new_invoices:
        obj.clean_fields(exclude={"contract"})
    for obj in new_items:
        obj.clean_fields(exclude={"invoice", "service"})
    for obj in new_payments:
        obj.clean_fields(exclude={"invoice", "received_by"})
    report = {
        "owner_id": str(owner_id), "periods": [str(period) for period in periods],
        "paid_through": str(paid_through), "contract_start_date": str(contract_start_date),
        "contract_end_date": str(contract_end_date), "updated_contracts": len(contracts_changed),
        "new_invoices": len(new_invoices), "new_payments": len(new_payments),
        "updated_invoices": len(invoices_changed), "target_invoices": len(targets),
        "payment_amount": str(sum((payment.amount for payment in new_payments), Decimal("0"))),
        "months": [{"period": str(period), "invoices": sum(inv.period == period for inv in targets),
                    "total": str(sum((inv.total_amount for inv in targets if inv.period == period), Decimal("0"))),
                    "paid": str(sum((inv.paid_amount for inv in targets if inv.period == period), Decimal("0")))}
                   for period in periods],
    }
    return dict(contracts_changed=contracts_changed, new_invoices=new_invoices, new_items=new_items,
                new_payments=new_payments, invoices_changed=invoices_changed, before=before, report=report)


def apply_backfill(plan):
    """Apply an already locked plan within the caller's atomic transaction."""
    Contract.objects.bulk_update(plan["contracts_changed"], ["code", "notes", "start_date", "end_date", "updated_at"], batch_size=100)
    Invoice.objects.bulk_create(plan["new_invoices"], batch_size=100)
    InvoiceItem.objects.bulk_create(plan["new_items"], batch_size=100)
    Payment.objects.bulk_create(plan["new_payments"], batch_size=100)
    Invoice.objects.bulk_update(plan["invoices_changed"], ["paid_amount", "status", "updated_at"], batch_size=100)


class Command(BaseCommand):
    help = "Backfill rent invoices and payments for explicitly selected periods, preserving existing entries."

    def add_arguments(self, parser):
        parser.add_argument("--owner-id", type=uuid.UUID, required=True)
        parser.add_argument("--allocation-backup", type=Path, required=True)
        parser.add_argument("--periods", nargs="+", type=month, required=True, help="Months in YYYY-MM format.")
        parser.add_argument("--contract-start-date", type=date.fromisoformat, required=True)
        parser.add_argument("--contract-end-date", type=date.fromisoformat, required=True)
        parser.add_argument("--paid-through", type=month, required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup-dir", type=Path, default=Path(settings.BASE_DIR) / "tmp" / "contract-backups")

    def handle(self, *args, **options):
        backup_path = None
        with transaction.atomic():
            plan = prepare_backfill(**{key: options[key] for key in (
                "owner_id", "allocation_backup", "periods", "contract_start_date", "contract_end_date", "paid_through",
            )}, lock=options["apply"])
            report = plan["report"]
            report["applied"] = False
            if options["apply"] and any(plan[key] for key in ("contracts_changed", "new_invoices", "new_payments", "invoices_changed")):
                snapshot = {
                    "state": "prepared", "prepared_at": timezone.now().isoformat(), "plan": report,
                    "before": plan["before"],
                    "new_invoice_ids": [str(invoice.id) for invoice in plan["new_invoices"]],
                    "new_item_ids": [str(item.id) for item in plan["new_items"]],
                    "new_payment_ids": [str(payment.id) for payment in plan["new_payments"]],
                    "updated_contract_ids": [str(contract.id) for contract in plan["contracts_changed"]],
                    "updated_invoice_ids": [str(invoice.id) for invoice in plan["invoices_changed"]],
                }
                directory = options["backup_dir"]
                directory.mkdir(parents=True, exist_ok=True)
                backup_path = directory / f"billing-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.json"
                with backup_path.open("x", encoding="utf-8") as output:
                    json.dump(snapshot, output, ensure_ascii=False, indent=2, default=str)
                apply_backfill(plan)
            if options["apply"]:
                report["applied"] = True
        if backup_path:
            snapshot["state"] = "committed"
            snapshot["committed_at"] = timezone.now().isoformat()
            with backup_path.open("w", encoding="utf-8") as output:
                json.dump(snapshot, output, ensure_ascii=False, indent=2, default=str)
            report["backup"] = str(backup_path)
        self.stdout.write(json.dumps(report, ensure_ascii=True))
