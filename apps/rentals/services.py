import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    Building,
    Contract,
    ContractMember,
    ContractService,
    Incident,
    Invoice,
    InvoiceItem,
    MeterReading,
    Notification,
    Payment,
    Room,
    Service,
    Tenant,
)


def notify_contract_tenants(
    contract: Contract,
    title: str,
    content: str,
    created_by=None,
) -> list[Notification]:
    user_ids = set()
    if contract.representative_id and contract.representative.user_id:
        user_ids.add(contract.representative.user_id)
    member_user_ids = (
        contract.members.filter(left_date__isnull=True, tenant__user__isnull=False)
        .values_list("tenant__user_id", flat=True)
    )
    user_ids.update(member_user_ids)
    building = contract.room.building if contract.room_id else None
    notifications = [
        Notification(
            title=title,
            content=content,
            recipient_id=uid,
            building=building,
            created_by=created_by,
        )
        for uid in user_ids
    ]
    if notifications:
        return Notification.objects.bulk_create(notifications)
    return []


@transaction.atomic
def activate_contract(contract: Contract) -> Contract:
    contract = Contract.objects.select_for_update().select_related("room__building").get(pk=contract.pk)
    Room.objects.select_for_update().get(pk=contract.room_id)
    if contract.status != Contract.Status.DRAFT:
        raise ValidationError("Chỉ có thể kích hoạt hợp đồng đang ở trạng thái bản nháp.")
    contract.status = Contract.Status.ACTIVE
    contract.full_clean()
    contract.save(update_fields=("status", "updated_at"))
    Room.objects.filter(pk=contract.room_id).update(status=Room.Status.OCCUPIED)
    if contract.representative_id:
        Tenant.objects.filter(pk=contract.representative_id, owner__isnull=True).update(
            owner_id=contract.room.building.owner_id
        )
    return contract


@transaction.atomic
def renew_contract(
    contract: Contract,
    new_end_date: date,
    new_monthly_rent: Decimal | None = None,
    notes: str = "",
) -> Contract:
    contract = Contract.objects.select_for_update().select_related("room").get(pk=contract.pk)
    Room.objects.select_for_update().get(pk=contract.room_id)
    if contract.status not in {Contract.Status.ACTIVE, Contract.Status.EXPIRED}:
        raise ValidationError("Chỉ có thể gia hạn hợp đồng đang hiệu lực hoặc đã hết hạn.")
    if not new_end_date or new_end_date <= contract.end_date:
        raise ValidationError({"new_end_date": "Ngày kết thúc gia hạn phải sau ngày kết thúc hiện tại."})
    contract.end_date = new_end_date
    if new_monthly_rent is not None:
        if new_monthly_rent < 0:
            raise ValidationError({"new_monthly_rent": "Giá thuê không được âm."})
        contract.monthly_rent = new_monthly_rent
    if notes:
        contract.notes = f"{contract.notes}\n[Gia hạn đến {new_end_date:%d/%m/%Y}]: {notes}".strip()
    contract.status = Contract.Status.ACTIVE
    contract.full_clean()
    contract.save(update_fields=("end_date", "monthly_rent", "notes", "status", "updated_at"))
    Room.objects.filter(pk=contract.room_id).update(status=Room.Status.OCCUPIED)
    return contract


@transaction.atomic
def terminate_contract(contract: Contract, reason: str = "") -> Contract:
    contract = Contract.objects.select_for_update().get(pk=contract.pk)
    Room.objects.select_for_update().get(pk=contract.room_id)
    if contract.status != Contract.Status.ACTIVE:
        raise ValidationError("Chỉ có thể chấm dứt hợp đồng đang hiệu lực.")
    contract.status = Contract.Status.TERMINATED
    if reason:
        contract.notes = f"{contract.notes}\n[Chấm dứt]: {reason}".strip()
    contract.save(update_fields=("status", "notes", "updated_at"))
    has_other_contract = (
        Contract.objects.filter(room_id=contract.room_id, status=Contract.Status.ACTIVE)
        .exclude(pk=contract.pk)
        .exists()
    )
    if not has_other_contract:
        Room.objects.filter(pk=contract.room_id).update(status=Room.Status.AVAILABLE)
    return contract


@transaction.atomic
def cancel_contract(contract: Contract, reason: str = "") -> Contract:
    contract = Contract.objects.select_for_update().get(pk=contract.pk)
    Room.objects.select_for_update().get(pk=contract.room_id)
    if contract.status in {Contract.Status.TERMINATED, Contract.Status.CANCELLED}:
        raise ValidationError("Không thể hủy hợp đồng đã chấm dứt hoặc đã hủy.")
    if (
        contract.status == Contract.Status.ACTIVE
        and contract.invoices.exclude(status=Invoice.Status.CANCELLED).exists()
    ):
        raise ValidationError(
            "Hợp đồng đang hiệu lực đã phát sinh hóa đơn, vui lòng sử dụng chức năng chấm dứt hợp đồng."
        )
    contract.status = Contract.Status.CANCELLED
    if reason:
        contract.notes = f"{contract.notes}\n[Hủy]: {reason}".strip()
    contract.save(update_fields=("status", "notes", "updated_at"))
    has_other_contract = (
        Contract.objects.filter(room_id=contract.room_id, status=Contract.Status.ACTIVE)
        .exclude(pk=contract.pk)
        .exists()
    )
    if not has_other_contract:
        Room.objects.filter(pk=contract.room_id, status=Room.Status.OCCUPIED).update(
            status=Room.Status.AVAILABLE
        )
    return contract


@transaction.atomic
def add_contract_member(
    contract: Contract,
    tenant: Tenant,
    joined_date: date,
    left_date: date | None = None,
) -> ContractMember:
    contract = Contract.objects.select_for_update().select_related("room__building").get(pk=contract.pk)
    if contract.status in {Contract.Status.TERMINATED, Contract.Status.CANCELLED}:
        raise ValidationError("Không thể thêm người ở cùng vào hợp đồng đã chấm dứt hoặc đã hủy.")
    if left_date and left_date < joined_date:
        raise ValidationError("Ngày rời đi không được nhỏ hơn ngày vào ở.")
    if ContractMember.objects.filter(contract=contract, tenant=tenant).exists():
        raise ValidationError("Khách thuê này đã là thành viên trong hợp đồng.")
    if left_date is None and contract.room.max_occupants:
        current_ids = {contract.representative_id} | set(
            contract.members.filter(left_date__isnull=True).values_list("tenant_id", flat=True)
        )
        if tenant.pk not in current_ids and len(current_ids) >= contract.room.max_occupants:
            raise ValidationError(
                f"Phòng {contract.room.number} chỉ cho phép tối đa {contract.room.max_occupants} người ở."
            )
    member = ContractMember.objects.create(
        contract=contract,
        tenant=tenant,
        joined_date=joined_date,
        left_date=left_date,
    )
    if tenant.owner_id is None:
        Tenant.objects.filter(pk=tenant.pk, owner__isnull=True).update(
            owner_id=contract.room.building.owner_id
        )
    return member


@transaction.atomic
def remove_contract_member(contract: Contract, member_id) -> None:
    contract = Contract.objects.select_for_update().get(pk=contract.pk)
    if contract.status in {Contract.Status.TERMINATED, Contract.Status.CANCELLED}:
        raise ValidationError("Không thể xóa thành viên khỏi hợp đồng đã chấm dứt hoặc đã hủy.")
    member = ContractMember.objects.filter(contract=contract, pk=member_id).first()
    if not member:
        raise ValidationError("Không tìm thấy thành viên hợp đồng.")
    member.delete()


@transaction.atomic
def attach_contract_service(
    contract: Contract,
    service: Service,
    unit_price: Decimal | None = None,
    quantity: Decimal = Decimal("1"),
    is_active: bool = True,
) -> ContractService:
    contract = Contract.objects.select_for_update().get(pk=contract.pk)
    if contract.status in {Contract.Status.TERMINATED, Contract.Status.CANCELLED}:
        raise ValidationError("Không thể gắn dịch vụ cho hợp đồng đã chấm dứt hoặc đã hủy.")
    applied_price = service.unit_price if unit_price is None else unit_price
    if applied_price < 0:
        raise ValidationError("Đơn giá dịch vụ không được âm.")
    if quantity <= 0:
        raise ValidationError("Số lượng dịch vụ phải lớn hơn 0.")
    cs, _ = ContractService.objects.update_or_create(
        contract=contract,
        service=service,
        defaults={
            "unit_price": applied_price,
            "quantity": quantity,
            "is_active": is_active,
        },
    )
    return cs


@transaction.atomic
def remove_contract_service(contract: Contract, contract_service_id) -> None:
    contract = Contract.objects.select_for_update().get(pk=contract.pk)
    if contract.status in {Contract.Status.TERMINATED, Contract.Status.CANCELLED}:
        raise ValidationError("Không thể xóa dịch vụ khỏi hợp đồng đã chấm dứt hoặc đã hủy.")
    cs = ContractService.objects.filter(contract=contract, pk=contract_service_id).first()
    if not cs:
        raise ValidationError("Không tìm thấy dịch vụ trong hợp đồng.")
    cs.delete()


def get_previous_meter_reading_value(room: Room, meter_type: str, period: date) -> Decimal:
    prev = (
        MeterReading.objects.filter(room=room, meter_type=meter_type, period__lt=period)
        .order_by("-period", "-recorded_at")
        .first()
    )
    return prev.current_value if prev else Decimal("0.00")


def _get_contract_occupant_count(contract: Contract, period: date) -> int:
    last_day = calendar.monthrange(period.year, period.month)[1]
    period_end = date(period.year, period.month, last_day)
    occupant_ids = {contract.representative_id}
    active_members = contract.members.filter(
        joined_date__lte=period_end,
    ).filter(Q(left_date__isnull=True) | Q(left_date__gte=period))
    occupant_ids.update(active_members.values_list("tenant_id", flat=True))
    return max(1, len(occupant_ids))


@transaction.atomic
def create_monthly_invoice(
    contract: Contract,
    period: date,
    due_date: date,
    *,
    status: str = Invoice.Status.ISSUED,
    surcharge: Decimal = Decimal("0"),
    surcharge_description: str = "Phụ thu",
    discount: Decimal = Decimal("0"),
    notes: str = "",
    created_by=None,
) -> Invoice:
    if period.day != 1:
        raise ValidationError("Kỳ hóa đơn phải là ngày đầu tiên của tháng.")
    contract = (
        Contract.objects.select_for_update()
        .select_related("room__building", "representative")
        .get(pk=contract.pk)
    )
    if contract.status != Contract.Status.ACTIVE:
        raise ValidationError("Chỉ có thể lập hóa đơn cho hợp đồng đang hiệu lực.")
    if discount < 0:
        raise ValidationError("Số tiền giảm trừ không được âm.")
    if surcharge < 0:
        raise ValidationError("Số tiền phụ thu không được âm.")
    if (
        Invoice.objects.filter(contract=contract, period=period)
        .exclude(status=Invoice.Status.CANCELLED)
        .exists()
    ):
        raise ValidationError(f"Hợp đồng {contract.code} đã có hóa đơn cho kỳ {period:%m/%Y}.")

    base_code = f"HD-{period:%Y%m}-{str(contract.id)[:8].upper()}"
    code = base_code
    suffix = 2
    while Invoice.objects.filter(code=code).exists():
        code = f"{base_code}-{suffix}"
        suffix += 1

    invoice = Invoice.objects.create(
        code=code,
        contract=contract,
        period=period,
        issued_date=date.today(),
        due_date=due_date,
        discount=discount,
        status=status,
        notes=notes,
    )

    # 1. Room rent item
    InvoiceItem.objects.create(
        invoice=invoice,
        description=f"Tiền phòng tháng {period:%m/%Y}",
        quantity=Decimal("1"),
        unit_price=contract.monthly_rent,
        amount=contract.monthly_rent,
    )

    # 2. Meter readings & ContractService items
    elec_reading = MeterReading.objects.filter(
        room=contract.room,
        meter_type=MeterReading.MeterType.ELECTRICITY,
        period=period,
    ).first()
    water_reading = MeterReading.objects.filter(
        room=contract.room,
        meter_type=MeterReading.MeterType.WATER,
        period=period,
    ).first()

    handled_elec = False
    handled_water = False
    occupant_count = Decimal(str(_get_contract_occupant_count(contract, period)))

    contract_services = (
        contract.contract_services.filter(is_active=True, service__is_active=True)
        .select_related("service")
        .order_by("created_at")
    )
    for cs in contract_services:
        srv = cs.service
        unit_price = cs.unit_price
        if srv.unit == Service.Unit.KWH:
            handled_elec = True
            if elec_reading and elec_reading.consumption > 0:
                qty = elec_reading.consumption
                InvoiceItem.objects.create(
                    invoice=invoice,
                    service=srv,
                    description=f"Tiền điện tháng {period:%m/%Y} ({elec_reading.previous_value} -> {elec_reading.current_value} kWh)",
                    quantity=qty,
                    unit_price=unit_price,
                    amount=qty * unit_price,
                )
        elif srv.unit == Service.Unit.CUBIC_METER:
            handled_water = True
            if water_reading and water_reading.consumption > 0:
                qty = water_reading.consumption
                InvoiceItem.objects.create(
                    invoice=invoice,
                    service=srv,
                    description=f"Tiền nước tháng {period:%m/%Y} ({water_reading.previous_value} -> {water_reading.current_value} m³)",
                    quantity=qty,
                    unit_price=unit_price,
                    amount=qty * unit_price,
                )
        elif srv.unit == Service.Unit.PERSON:
            qty = occupant_count if cs.quantity == Decimal("1") else cs.quantity
            InvoiceItem.objects.create(
                invoice=invoice,
                service=srv,
                description=f"{srv.name} tháng {period:%m/%Y} ({int(qty)} người)",
                quantity=qty,
                unit_price=unit_price,
                amount=qty * unit_price,
            )
        else:
            qty = cs.quantity
            InvoiceItem.objects.create(
                invoice=invoice,
                service=srv,
                description=f"{srv.name} tháng {period:%m/%Y}",
                quantity=qty,
                unit_price=unit_price,
                amount=qty * unit_price,
            )

    owner_id = contract.room.building.owner_id
    if not handled_elec and elec_reading and elec_reading.consumption > 0:
        elec_service = (
            Service.objects.filter(unit=Service.Unit.KWH, is_active=True)
            .filter(Q(owner_id=owner_id) | Q(owner__isnull=True))
            .order_by("-owner_id", "name")
            .first()
        )
        if elec_service:
            qty = elec_reading.consumption
            InvoiceItem.objects.create(
                invoice=invoice,
                service=elec_service,
                description=f"Tiền điện tháng {period:%m/%Y} ({elec_reading.previous_value} -> {elec_reading.current_value} kWh)",
                quantity=qty,
                unit_price=elec_service.unit_price,
                amount=qty * elec_service.unit_price,
            )

    if not handled_water and water_reading and water_reading.consumption > 0:
        water_service = (
            Service.objects.filter(unit=Service.Unit.CUBIC_METER, is_active=True)
            .filter(Q(owner_id=owner_id) | Q(owner__isnull=True))
            .order_by("-owner_id", "name")
            .first()
        )
        if water_service:
            qty = water_reading.consumption
            InvoiceItem.objects.create(
                invoice=invoice,
                service=water_service,
                description=f"Tiền nước tháng {period:%m/%Y} ({water_reading.previous_value} -> {water_reading.current_value} m³)",
                quantity=qty,
                unit_price=water_service.unit_price,
                amount=qty * water_service.unit_price,
            )

    # 3. Surcharge item if present
    if surcharge and surcharge > 0:
        InvoiceItem.objects.create(
            invoice=invoice,
            service=None,
            description=surcharge_description.strip() or f"Phụ thu tháng {period:%m/%Y}",
            quantity=Decimal("1"),
            unit_price=surcharge,
            amount=surcharge,
        )

    invoice = recalculate_invoice(invoice)
    if invoice.status in {Invoice.Status.ISSUED, Invoice.Status.OVERDUE}:
        notify_contract_tenants(
            contract,
            title=f"Hóa đơn mới {invoice.code} kỳ {period:%m/%Y}",
            content=(
                f"Hóa đơn {invoice.code} cho phòng {contract.room.number} kỳ {period:%m/%Y} "
                f"đã được phát hành với tổng số tiền {invoice.total_amount:,.0f} đ. "
                f"Hạn thanh toán: {invoice.due_date:%d/%m/%Y}."
            ),
            created_by=created_by,
        )
    return invoice


@transaction.atomic
def generate_bulk_invoices(
    contracts=None,
    period: date = None,
    due_date: date = None,
    *,
    contracts_queryset=None,
    status: str = Invoice.Status.DRAFT,
    created_by=None,
) -> tuple[list[Invoice], int]:
    if contracts is None:
        contracts = contracts_queryset
    if period.day != 1:
        raise ValidationError("Kỳ hóa đơn phải là ngày đầu tiên của tháng.")
    last_day = calendar.monthrange(period.year, period.month)[1]
    period_end = date(period.year, period.month, last_day)
    eligible_contracts = (
        contracts.filter(
            status=Contract.Status.ACTIVE,
            start_date__lte=period_end,
            end_date__gte=period,
        )
        .select_related("room__building", "representative")
    )
    created_invoices = []
    skipped_count = 0
    for contract in eligible_contracts:
        already_exists = (
            Invoice.objects.filter(contract=contract, period=period)
            .exclude(status=Invoice.Status.CANCELLED)
            .exists()
        )
        if already_exists:
            skipped_count += 1
            continue
        inv = create_monthly_invoice(
            contract,
            period,
            due_date,
            status=status,
            created_by=created_by,
        )
        created_invoices.append(inv)
    return created_invoices, skipped_count


@transaction.atomic
def recalculate_invoice(invoice: Invoice) -> Invoice:
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    subtotal = invoice.items.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    paid = invoice.payments.filter(is_void=False).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    invoice.subtotal = subtotal
    invoice.total_amount = max(subtotal - invoice.discount, Decimal("0"))
    invoice.paid_amount = paid

    if invoice.status != Invoice.Status.CANCELLED:
        if invoice.status == Invoice.Status.DRAFT and paid == Decimal("0"):
            pass
        elif paid >= invoice.total_amount and invoice.total_amount > Decimal("0"):
            invoice.status = Invoice.Status.PAID
        elif paid > Decimal("0"):
            invoice.status = Invoice.Status.PARTIAL
        else:
            if invoice.due_date and invoice.due_date < date.today():
                invoice.status = Invoice.Status.OVERDUE
            else:
                invoice.status = Invoice.Status.ISSUED

    invoice.save(update_fields=("subtotal", "total_amount", "paid_amount", "status", "updated_at"))
    return invoice


@transaction.atomic
def issue_invoice(invoice: Invoice, actor=None, issued_by=None) -> Invoice:
    actor = actor or issued_by
    invoice = Invoice.objects.select_for_update().select_related("contract__room__building", "contract__representative").get(pk=invoice.pk)
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError("Chỉ có thể phát hành hóa đơn đang ở trạng thái bản nháp.")
    invoice.issued_date = date.today()
    invoice.status = (
        Invoice.Status.OVERDUE
        if invoice.due_date and invoice.due_date < date.today()
        else Invoice.Status.ISSUED
    )
    invoice.save(update_fields=("issued_date", "status", "updated_at"))
    invoice = recalculate_invoice(invoice)
    notify_contract_tenants(
        invoice.contract,
        title=f"Hóa đơn {invoice.code} kỳ {invoice.period:%m/%Y} đã phát hành",
        content=(
            f"Hóa đơn {invoice.code} cho phòng {invoice.contract.room.number} kỳ {invoice.period:%m/%Y} "
            f"đã được phát hành. Tổng cần thanh toán: {invoice.total_amount:,.0f} đ. "
            f"Hạn thanh toán: {invoice.due_date:%d/%m/%Y}."
        ),
        created_by=actor,
    )
    return invoice


@transaction.atomic
def cancel_invoice(invoice: Invoice, reason: str, actor=None, cancelled_by=None) -> Invoice:
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Vui lòng nhập lý do hủy hóa đơn.")
    if invoice.status == Invoice.Status.CANCELLED:
        raise ValidationError("Hóa đơn này đã được hủy trước đó.")
    valid_paid = invoice.payments.filter(is_void=False).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    if valid_paid > Decimal("0"):
        raise ValidationError("Không thể hủy hóa đơn đã có giao dịch thanh toán. Vui lòng hủy giao dịch trước.")
    invoice.status = Invoice.Status.CANCELLED
    invoice.notes = f"{invoice.notes}\n[Hủy hóa đơn]: {reason}".strip()
    invoice.save(update_fields=("status", "notes", "updated_at"))
    return invoice


@transaction.atomic
def add_invoice_item(
    invoice: Invoice,
    *,
    description: str,
    quantity: Decimal,
    unit_price: Decimal,
    service: Service | None = None,
) -> InvoiceItem:
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError("Chỉ được chỉnh sửa chi tiết khi hóa đơn còn ở trạng thái bản nháp.")
    if quantity <= 0:
        raise ValidationError("Số lượng phải lớn hơn 0.")
    if unit_price < 0:
        raise ValidationError("Đơn giá không được âm.")
    item = InvoiceItem.objects.create(
        invoice=invoice,
        service=service,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        amount=quantity * unit_price,
    )
    recalculate_invoice(invoice)
    return item


@transaction.atomic
def remove_invoice_item(invoice: Invoice, item_id) -> None:
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError("Chỉ được xóa dòng chi tiết khi hóa đơn còn ở trạng thái bản nháp.")
    item = InvoiceItem.objects.filter(invoice=invoice, pk=item_id).first()
    if not item:
        raise ValidationError("Không tìm thấy mục chi tiết hóa đơn.")
    item.delete()
    recalculate_invoice(invoice)


@transaction.atomic
def record_payment(
    *,
    invoice: Invoice,
    amount: Decimal,
    paid_at,
    method: str,
    received_by,
    reference: str = "",
    notes: str = "",
) -> Payment:
    if amount <= 0:
        raise ValidationError("Số tiền thanh toán phải lớn hơn 0.")
    invoice = (
        Invoice.objects.select_for_update()
        .select_related("contract__room__building", "contract__representative")
        .get(pk=invoice.pk)
    )
    if invoice.status == Invoice.Status.DRAFT:
        raise ValidationError("Không thể thanh toán hóa đơn đang ở trạng thái bản nháp.")
    if invoice.status == Invoice.Status.CANCELLED:
        raise ValidationError("Không thể thanh toán hóa đơn đã hủy.")
    if invoice.status == Invoice.Status.PAID or invoice.balance <= Decimal("0"):
        raise ValidationError("Hóa đơn này đã được thanh toán đủ.")
    if amount > invoice.balance:
        raise ValidationError("Số tiền thanh toán vượt quá số dư còn nợ của hóa đơn.")
    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        paid_at=paid_at,
        method=method,
        received_by=received_by,
        reference=reference,
        notes=notes,
    )
    invoice = recalculate_invoice(invoice)
    notify_contract_tenants(
        invoice.contract,
        title=f"Xác nhận thanh toán hóa đơn {invoice.code}",
        content=(
            f"Hệ thống đã ghi nhận khoản thanh toán {amount:,.0f} đ cho hóa đơn {invoice.code} "
            f"(Phòng {invoice.contract.room.number}). Số tiền còn nợ: {invoice.balance:,.0f} đ."
        ),
        created_by=received_by,
    )
    return payment


@transaction.atomic
def void_payment(payment: Payment, reason: str = "", actor=None, voided_by=None) -> Payment:
    payment = Payment.objects.select_for_update().select_related("invoice").get(pk=payment.pk)
    invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
    if payment.is_void:
        raise ValidationError("Giao dịch thanh toán này đã được hủy trước đó.")
    payment.is_void = True
    if reason:
        payment.notes = f"{payment.notes}\n[Hủy giao dịch]: {reason.strip()}".strip()
    payment.save(update_fields=("is_void", "notes", "updated_at"))
    recalculate_invoice(invoice)
    return payment


@transaction.atomic
def update_incident_management(
    incident: Incident,
    *,
    priority: str,
    status: str,
    assigned_to=None,
    resolution_notes: str = "",
    actor=None,
    updated_by=None,
) -> Incident:
    actor = actor or updated_by
    incident = (
        Incident.objects.select_for_update(of=("self",))
        .select_related("room__building", "reported_by__user")
        .get(pk=incident.pk)
    )
    old_status = incident.status
    incident.priority = priority
    incident.status = status
    incident.assigned_to = assigned_to
    incident.resolution_notes = resolution_notes
    if status in {Incident.Status.RESOLVED, Incident.Status.CLOSED}:
        if incident.resolved_at is None:
            incident.resolved_at = timezone.now()
    else:
        incident.resolved_at = None
    incident.full_clean()
    incident.save(
        update_fields=(
            "priority",
            "status",
            "assigned_to",
            "resolution_notes",
            "resolved_at",
            "updated_at",
        )
    )
    if status != old_status and incident.reported_by_id and incident.reported_by.user_id:
        Notification.objects.create(
            title=f"Cập nhật sự cố: {incident.title}",
            content=(
                f"Sự cố '{incident.title}' tại phòng {incident.room.number} đã được chuyển sang "
                f"trạng thái '{incident.get_status_display()}'."
                + (f" Ghi chú xử lý: {resolution_notes}" if resolution_notes else "")
            ),
            recipient_id=incident.reported_by.user_id,
            building=incident.room.building,
            created_by=actor,
        )
    return incident


@transaction.atomic
def send_targeted_notifications(
    *,
    target_type: str,
    title: str,
    content: str,
    created_by,
    tenant: Tenant | None = None,
    room: Room | None = None,
    building: Building | None = None,
) -> list[Notification]:
    recipient_user_ids = set()
    target_building = None

    if target_type == "tenant":
        if not tenant:
            raise ValidationError("Vui lòng chọn khách thuê nhận thông báo.")
        if not tenant.user_id:
            raise ValidationError("Khách thuê này chưa được liên kết với tài khoản đăng nhập.")
        recipient_user_ids.add(tenant.user_id)
        active_c = (
            Contract.objects.filter(
                Q(representative=tenant) | Q(members__tenant=tenant),
                status=Contract.Status.ACTIVE,
            )
            .select_related("room__building")
            .first()
        )
        if active_c:
            target_building = active_c.room.building
    elif target_type == "room":
        if not room:
            raise ValidationError("Vui lòng chọn phòng nhận thông báo.")
        target_building = room.building
        active_contracts = Contract.objects.filter(room=room, status=Contract.Status.ACTIVE)
        rep_user_ids = active_contracts.filter(representative__user__isnull=False).values_list(
            "representative__user_id", flat=True
        )
        member_user_ids = ContractMember.objects.filter(
            contract__in=active_contracts,
            left_date__isnull=True,
            tenant__user__isnull=False,
        ).values_list("tenant__user_id", flat=True)
        recipient_user_ids.update(rep_user_ids)
        recipient_user_ids.update(member_user_ids)
        if not recipient_user_ids:
            raise ValidationError("Phòng này hiện không có khách thuê nào đã liên kết tài khoản.")
    elif target_type == "building":
        if not building:
            raise ValidationError("Vui lòng chọn tòa nhà nhận thông báo.")
        target_building = building
        active_contracts = Contract.objects.filter(
            room__building=building, status=Contract.Status.ACTIVE
        )
        rep_user_ids = active_contracts.filter(representative__user__isnull=False).values_list(
            "representative__user_id", flat=True
        )
        member_user_ids = ContractMember.objects.filter(
            contract__in=active_contracts,
            left_date__isnull=True,
            tenant__user__isnull=False,
        ).values_list("tenant__user_id", flat=True)
        recipient_user_ids.update(rep_user_ids)
        recipient_user_ids.update(member_user_ids)
        if not recipient_user_ids:
            raise ValidationError("Tòa nhà này hiện không có khách thuê nào đã liên kết tài khoản.")
    else:
        raise ValidationError("Loại đối tượng nhận thông báo không hợp lệ.")

    notifications = [
        Notification(
            title=title,
            content=content,
            recipient_id=uid,
            building=target_building,
            created_by=created_by,
        )
        for uid in recipient_user_ids
    ]
    return Notification.objects.bulk_create(notifications)


@transaction.atomic
def notify_expiring_contracts(contracts_qs, *, days: int = 30, actor=None, created_by=None) -> list[Notification]:
    actor = actor or created_by
    today = date.today()
    deadline = today + timedelta(days=days)
    expiring = contracts_qs.filter(
        status=Contract.Status.ACTIVE,
        end_date__gte=today,
        end_date__lte=deadline,
    ).select_related("room__building", "representative")
    created = []
    for contract in expiring:
        title = f"Hợp đồng {contract.code} sắp hết hạn ({contract.end_date:%d/%m/%Y})"
        content = (
            f"Hợp đồng {contract.code} tại phòng {contract.room.number} ({contract.room.building.name}) "
            f"sẽ hết hạn vào ngày {contract.end_date:%d/%m/%Y}. Vui lòng liên hệ quản lý để gia hạn hoặc thanh lý."
        )
        created.extend(notify_contract_tenants(contract, title=title, content=content, created_by=actor))
    return created

