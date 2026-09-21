from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import Contract, Invoice, InvoiceItem, Payment, Room


@transaction.atomic
def activate_contract(contract: Contract) -> Contract:
    contract = Contract.objects.select_for_update().select_related("room").get(pk=contract.pk)
    Room.objects.select_for_update().get(pk=contract.room_id)
    contract.status = Contract.Status.ACTIVE
    contract.full_clean()
    contract.save(update_fields=("status", "updated_at"))
    Room.objects.filter(pk=contract.room_id).update(status=Room.Status.OCCUPIED)
    return contract


@transaction.atomic
def terminate_contract(contract: Contract) -> Contract:
    contract = Contract.objects.select_for_update().get(pk=contract.pk)
    contract.status = Contract.Status.TERMINATED
    contract.save(update_fields=("status", "updated_at"))
    has_other_contract = Contract.objects.filter(room_id=contract.room_id, status=Contract.Status.ACTIVE).exclude(pk=contract.pk).exists()
    if not has_other_contract:
        Room.objects.filter(pk=contract.room_id).update(status=Room.Status.AVAILABLE)
    return contract


@transaction.atomic
def create_monthly_invoice(contract: Contract, period: date, due_date: date) -> Invoice:
    if period.day != 1:
        raise ValidationError("Kỳ hóa đơn phải là ngày đầu tiên của tháng.")
    if contract.status != Contract.Status.ACTIVE:
        raise ValidationError("Chỉ có thể lập hóa đơn cho hợp đồng đang hiệu lực.")
    code = f"HD-{period:%Y%m}-{str(contract.id)[:8].upper()}"
    invoice, created = Invoice.objects.get_or_create(
        contract=contract,
        period=period,
        defaults={
            "code": code,
            "issued_date": date.today(),
            "due_date": due_date,
            "status": Invoice.Status.DRAFT,
        },
    )
    if created:
        InvoiceItem.objects.create(
            invoice=invoice,
            description=f"Tiền phòng tháng {period:%m/%Y}",
            quantity=Decimal("1"),
            unit_price=contract.monthly_rent,
            amount=contract.monthly_rent,
        )
        invoice = recalculate_invoice(invoice)
    return invoice


@transaction.atomic
def recalculate_invoice(invoice: Invoice) -> Invoice:
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    subtotal = invoice.items.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    invoice.subtotal = subtotal
    invoice.total_amount = max(subtotal - invoice.discount, Decimal("0"))
    invoice.save(update_fields=("subtotal", "total_amount", "updated_at"))
    return invoice


@transaction.atomic
def record_payment(*, invoice: Invoice, amount: Decimal, paid_at, method: str, received_by, reference: str = "") -> Payment:
    if amount <= 0:
        raise ValidationError("Số tiền thanh toán phải lớn hơn 0.")
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status == Invoice.Status.CANCELLED:
        raise ValidationError("Không thể thanh toán hóa đơn đã hủy.")
    if amount > invoice.balance:
        raise ValidationError("Số tiền thanh toán vượt quá số dư hóa đơn.")
    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        paid_at=paid_at,
        method=method,
        received_by=received_by,
        reference=reference,
    )
    paid = invoice.payments.filter(is_void=False).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    invoice.paid_amount = paid
    invoice.status = Invoice.Status.PAID if paid >= invoice.total_amount else Invoice.Status.PARTIAL
    invoice.save(update_fields=("paid_amount", "status", "updated_at"))
    return payment
