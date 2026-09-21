from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.rentals.models import (
    Amenity,
    Building,
    Contract,
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
from apps.rentals.services import create_monthly_invoice, recalculate_invoice, record_payment


class Command(BaseCommand):
    help = "Tạo dữ liệu demo phong phú và có thể chạy lặp lại an toàn"

    def handle(self, *args, **options):
        User = get_user_model()
        admin = self._user(User, "admin", "Admin@123456", User.Role.ADMIN, "Quản trị", "Hệ thống", True)
        owner = self._user(User, "chunha", "Chunha@123456", User.Role.OWNER, "Ngọc", "Trần", True)
        staff = self._user(User, "nhanvien", "Nhanvien@123456", User.Role.STAFF, "Hương", "Lê", True)
        tenant_user = self._user(User, "khachthue", "Khach@123456", User.Role.TENANT, "Minh", "Nguyễn Văn")
        tenant_user_2 = self._user(User, "lananh", "Khach@123456", User.Role.TENANT, "Lan Anh", "Trần")
        buildings = self._buildings(owner)
        amenities = self._amenities()
        rooms = self._rooms(buildings, amenities)
        tenants = self._tenants(tenant_user, tenant_user_2)
        services = self._services()
        contracts = self._contracts(rooms, tenants)
        self._meters(rooms, admin)
        self._invoices(contracts, services, admin)
        self._incidents(rooms, tenants, staff)
        self._notifications(tenant_user, tenant_user_2)
        self.stdout.write(self.style.SUCCESS(
            "Demo data created. Admin: admin / Admin@123456; Owner: chunha / Chunha@123456; "
            "Staff: nhanvien / Nhanvien@123456; Tenant: khachthue / Khach@123456"
        ))

    def _user(self, User, username, password, role, first_name, last_name, is_staff=False):
        user, created = User.objects.get_or_create(username=username, defaults={
            "email": f"{username}@example.com", "first_name": first_name, "last_name": last_name,
            "role": role, "is_staff": is_staff, "is_superuser": role == User.Role.ADMIN,
            "phone": "0901234567" if role == User.Role.OWNER else "",
        })
        if created:
            user.set_password(password)
            user.save()
        return user

    def _buildings(self, owner):
        data = [
            ("Khu trọ Bình An", "25 Nguyễn Gia Trí, Bình Thạnh, TP.HCM", "Gần trường đại học, an ninh 24/7."),
            ("An Tâm Residence", "118 Nguyễn Thị Minh Khai, Quận 3, TP.HCM", "Tòa nhà hiện đại ngay trung tâm, có thang máy."),
            ("Nhà trọ Sinh Viên", "42 Linh Trung, TP. Thủ Đức, TP.HCM", "Không gian yên tĩnh, gần khu đại học."),
            ("Căn hộ Mini Riverside", "86 Bến Vân Đồn, Quận 4, TP.HCM", "Căn hộ mini gần trung tâm và bờ sông."),
            ("Tòa nhà Ngũ Phúc", "55 Phan Văn Trị, Gò Vấp, TP.HCM", "Tòa nhà 5 tầng, mỗi tầng một phòng riêng tư và thoáng mát."),
        ]
        return [Building.objects.get_or_create(name=n, defaults={"address": a, "description": d, "owner": owner})[0] for n, a, d in data]

    def _amenities(self):
        names = ("Máy lạnh", "Tủ lạnh", "Máy giặt chung", "Ban công", "Gác lửng", "Bếp riêng", "Thang máy", "Bãi xe", "Camera an ninh", "Wi-Fi")
        return {name: Amenity.objects.get_or_create(name=name)[0] for name in names}

    def _rooms(self, buildings, amenities):
        specs = [
            (0, "101", 1, "24", "3500000", Room.Status.OCCUPIED, ("Máy lạnh", "Bếp riêng", "Wi-Fi")),
            (0, "102", 2, "22", "3200000", Room.Status.AVAILABLE, ("Máy lạnh", "Gác lửng", "Bãi xe")),
            (0, "201", 3, "28", "3900000", Room.Status.AVAILABLE, ("Ban công", "Máy lạnh", "Bếp riêng")),
            (0, "202", 4, "20", "2900000", Room.Status.MAINTENANCE, ("Gác lửng", "Wi-Fi")),
            (0, "501", 5, "30", "4200000", Room.Status.AVAILABLE, ("Ban công", "Máy lạnh", "Bếp riêng", "Wi-Fi")),
            (1, "A01", 1, "30", "5200000", Room.Status.OCCUPIED, ("Thang máy", "Máy lạnh", "Tủ lạnh", "Bếp riêng")),
            (1, "A02", 2, "27", "4800000", Room.Status.AVAILABLE, ("Thang máy", "Máy lạnh", "Ban công")),
            (1, "B01", 3, "32", "5600000", Room.Status.AVAILABLE, ("Thang máy", "Máy lạnh", "Tủ lạnh", "Ban công")),
            (1, "C01", 4, "34", "5900000", Room.Status.AVAILABLE, ("Thang máy", "Máy lạnh", "Tủ lạnh", "Bếp riêng")),
            (1, "D01", 5, "36", "6200000", Room.Status.AVAILABLE, ("Thang máy", "Máy lạnh", "Tủ lạnh", "Ban công")),
            (2, "S01", 1, "18", "2200000", Room.Status.OCCUPIED, ("Gác lửng", "Bãi xe", "Wi-Fi")),
            (2, "S02", 2, "18", "2300000", Room.Status.AVAILABLE, ("Gác lửng", "Bãi xe", "Wi-Fi")),
            (2, "S03", 3, "20", "2500000", Room.Status.RESERVED, ("Máy lạnh", "Bãi xe", "Wi-Fi")),
            (2, "S04", 4, "21", "2700000", Room.Status.AVAILABLE, ("Máy lạnh", "Gác lửng", "Bãi xe", "Wi-Fi")),
            (2, "S05", 5, "22", "2900000", Room.Status.AVAILABLE, ("Máy lạnh", "Ban công", "Bãi xe", "Wi-Fi")),
            (3, "R01", 1, "35", "6500000", Room.Status.AVAILABLE, ("Máy lạnh", "Tủ lạnh", "Máy giặt chung", "Ban công", "Bếp riêng")),
            (3, "R02", 2, "38", "7200000", Room.Status.AVAILABLE, ("Máy lạnh", "Tủ lạnh", "Ban công", "Bếp riêng", "Thang máy")),
            (3, "R03", 3, "38", "7400000", Room.Status.AVAILABLE, ("Máy lạnh", "Tủ lạnh", "Ban công", "Bếp riêng", "Thang máy")),
            (3, "R04", 4, "40", "7800000", Room.Status.AVAILABLE, ("Máy lạnh", "Tủ lạnh", "Máy giặt chung", "Ban công", "Bếp riêng")),
            (3, "R05", 5, "42", "8200000", Room.Status.AVAILABLE, ("Máy lạnh", "Tủ lạnh", "Ban công", "Bếp riêng", "Thang máy")),
            (4, "P101", 1, "24", "3200000", Room.Status.AVAILABLE, ("Máy lạnh", "Bếp riêng", "Bãi xe", "Wi-Fi")),
            (4, "P201", 2, "25", "3300000", Room.Status.AVAILABLE, ("Máy lạnh", "Bếp riêng", "Bãi xe", "Wi-Fi")),
            (4, "P301", 3, "26", "3400000", Room.Status.AVAILABLE, ("Máy lạnh", "Ban công", "Bếp riêng", "Wi-Fi")),
            (4, "P401", 4, "27", "3500000", Room.Status.AVAILABLE, ("Máy lạnh", "Ban công", "Bếp riêng", "Thang máy")),
            (4, "P501", 5, "28", "3600000", Room.Status.AVAILABLE, ("Máy lạnh", "Ban công", "Bếp riêng", "Thang máy")),
        ]
        result = {}
        for building_index, number, floor, area, rent, status, room_amenities in specs:
            room, _ = Room.objects.update_or_create(building=buildings[building_index], number=number, defaults={
                "floor": floor, "area": Decimal(area), "monthly_rent": Decimal(rent), "deposit_amount": Decimal(rent),
                "max_occupants": 3 if Decimal(area) >= 28 else 2, "status": status,
                "description": "Phòng sạch đẹp, thoáng mát, giờ giấc tự do và khu vực an ninh.",
            })
            room.amenities.set(amenities[name] for name in room_amenities)
            result[f"{building_index}-{number}"] = room

        # Mỗi tòa có 5 tầng và đúng 5 phòng mỗi tầng (25 phòng/tòa).
        standard_amenities = (amenities["Máy lạnh"], amenities["Bãi xe"], amenities["Wi-Fi"])
        for building_index, building in enumerate(buildings):
            for floor in range(1, 6):
                missing = 5 - building.rooms.filter(floor=floor).count()
                for slot in range(1, missing + 1):
                    number = f"F{floor}-{slot:02d}"
                    suffix = slot
                    while building.rooms.filter(number=number).exists():
                        suffix += 1
                        number = f"F{floor}-{suffix:02d}"
                    monthly_rent = Decimal(2_600_000 + building_index * 450_000 + floor * 120_000 + slot * 50_000)
                    room = Room.objects.create(
                        building=building,
                        number=number,
                        floor=floor,
                        area=Decimal(20 + floor + slot),
                        monthly_rent=monthly_rent,
                        deposit_amount=monthly_rent,
                        max_occupants=2 if slot < 4 else 3,
                        status=Room.Status.AVAILABLE,
                        description="Phòng sạch đẹp, đủ ánh sáng, giờ giấc tự do và khu vực an ninh.",
                    )
                    room.amenities.set(standard_amenities)
        return result

    def _tenants(self, user_1, user_2):
        data = [
            ("079000000001", "Nguyễn Văn Minh", "0900000001", user_1),
            ("079000000002", "Trần Lan Anh", "0900000002", user_2),
            ("079000000003", "Lê Quốc Bảo", "0900000003", None),
            ("079000000004", "Phạm Thu Hà", "0900000004", None),
            ("079000000005", "Võ Minh Khang", "0900000005", None),
        ]
        result = []
        for identity, full_name, phone, user in data:
            tenant, _ = Tenant.objects.get_or_create(identity_number=identity, defaults={
                "full_name": full_name, "phone": phone, "email": f"{phone}@example.com", "user": user,
            })
            if user and tenant.user_id != user.id:
                tenant.user = user
                tenant.save(update_fields=("user", "updated_at"))
            result.append(tenant)
        return result

    def _services(self):
        data = [
            ("Điện", Service.Unit.KWH, "4000", True), ("Nước", Service.Unit.CUBIC_METER, "20000", True),
            ("Internet", Service.Unit.ROOM, "120000", False), ("Rác và vệ sinh", Service.Unit.PERSON, "50000", False),
            ("Phí giữ xe", Service.Unit.PERSON, "100000", False),
        ]
        return {
            name: Service.objects.update_or_create(
                name=name,
                defaults={"unit": unit, "unit_price": Decimal(price), "is_metered": metered},
            )[0]
            for name, unit, price, metered in data
        }

    def _contracts(self, rooms, tenants):
        period = date.today().replace(day=1)
        specs = [
            (f"HD-{period.year}-0001", "HD-DEMO-001", "0-101", 0, period - timedelta(days=150), period + timedelta(days=215)),
            (f"HD-{period.year}-0002", "HD-DEMO-002", "1-A01", 1, period - timedelta(days=90), period + timedelta(days=275)),
            (f"HD-{period.year}-0003", "HD-DEMO-003", "2-S01", 2, period - timedelta(days=210), period + timedelta(days=155)),
        ]
        result = []
        for code, legacy_code, room_key, tenant_index, start, end in specs:
            room = rooms[room_key]
            legacy_contract = Contract.objects.filter(code=legacy_code).first()
            if legacy_contract and not Contract.objects.filter(code=code).exists():
                legacy_contract.code = code
                legacy_contract.save(update_fields=("code", "updated_at"))
            result.append(Contract.objects.get_or_create(code=code, defaults={
                "room": room, "representative": tenants[tenant_index], "start_date": start, "end_date": end,
                "monthly_rent": room.monthly_rent, "deposit_amount": room.deposit_amount, "status": Contract.Status.ACTIVE,
            })[0])
        return result

    def _meters(self, rooms, admin):
        period = date.today().replace(day=1)
        for index, room_key in enumerate(("0-101", "1-A01", "2-S01")):
            for meter_type, previous, current in (
                (MeterReading.MeterType.ELECTRICITY, 1000 + index * 240, 1085 + index * 260),
                (MeterReading.MeterType.WATER, 120 + index * 30, 128 + index * 32),
            ):
                MeterReading.objects.get_or_create(room=rooms[room_key], meter_type=meter_type, period=period, defaults={
                    "previous_value": previous, "current_value": current, "recorded_by": admin,
                })

    def _invoices(self, contracts, services, admin):
        current = date.today().replace(day=1)
        periods = ((current - timedelta(days=5)).replace(day=1), current)
        for contract_index, contract in enumerate(contracts):
            for period_index, period in enumerate(periods):
                invoice = create_monthly_invoice(contract, period, period + timedelta(days=9))
                extras = [
                    (services["Điện"], "Tiền điện", Decimal(75 + contract_index * 8)),
                    (services["Nước"], "Tiền nước", Decimal(7 + contract_index)),
                    (services["Internet"], "Internet", Decimal(1)),
                    (services["Rác và vệ sinh"], "Rác và vệ sinh", Decimal(1)),
                ]
                for service, description, quantity in extras:
                    InvoiceItem.objects.update_or_create(invoice=invoice, description=description, defaults={
                        "service": service, "quantity": quantity, "unit_price": service.unit_price,
                        "amount": quantity * service.unit_price,
                    })
                invoice = recalculate_invoice(invoice)
                target_payment = None
                if period_index == 0:
                    target_payment = invoice.total_amount
                elif period_index == 1 and contract_index == 1:
                    target_payment = (invoice.total_amount / 2).quantize(Decimal("1"))

                existing_payment = invoice.payments.filter(is_void=False).first()
                if target_payment is not None and existing_payment:
                    existing_payment.amount = target_payment
                    existing_payment.save(update_fields=("amount", "updated_at"))
                    invoice.paid_amount = target_payment
                    invoice.status = Invoice.Status.PAID if target_payment >= invoice.total_amount else Invoice.Status.PARTIAL
                    invoice.save(update_fields=("paid_amount", "status", "updated_at"))
                elif target_payment is not None and period_index == 0:
                    paid_at = timezone.make_aware(datetime.combine(period + timedelta(days=5), datetime.min.time()))
                    record_payment(invoice=invoice, amount=target_payment, paid_at=paid_at,
                                   method=Payment.Method.TRANSFER, received_by=admin, reference=f"CK-{invoice.code}")
                elif target_payment is not None:
                    record_payment(invoice=invoice, amount=target_payment,
                                   paid_at=timezone.now(), method=Payment.Method.CASH, received_by=admin)
                elif invoice.status == Invoice.Status.DRAFT:
                    invoice.status = Invoice.Status.ISSUED
                    invoice.save(update_fields=("status", "updated_at"))

    def _incidents(self, rooms, tenants, staff):
        data = [
            ("0-101", 0, "Vòi nước bị rò", "Vòi nước khu bếp bị rò nhẹ.", Incident.Priority.MEDIUM, Incident.Status.IN_PROGRESS),
            ("1-A01", 1, "Máy lạnh không mát", "Máy lạnh hoạt động nhưng không đủ lạnh.", Incident.Priority.HIGH, Incident.Status.OPEN),
            ("2-S01", 2, "Đèn hành lang hỏng", "Đèn trước cửa phòng không sáng.", Incident.Priority.LOW, Incident.Status.RESOLVED),
        ]
        for room_key, tenant_index, title, description, priority, status in data:
            Incident.objects.get_or_create(room=rooms[room_key], title=title, defaults={
                "reported_by": tenants[tenant_index], "description": description, "priority": priority,
                "status": status, "assigned_to": staff,
            })

    def _notifications(self, user_1, user_2):
        data = [
            (user_1, "Chào mừng bạn đến cổng người thuê", "Bạn có thể xem hợp đồng, hóa đơn và gửi yêu cầu hỗ trợ tại đây."),
            (user_1, "Hóa đơn tháng mới", "Hóa đơn tháng này đã được phát hành. Vui lòng thanh toán trước ngày đến hạn."),
            (user_1, "Lịch bảo trì hệ thống nước", "Hệ thống nước sẽ được kiểm tra từ 09:00 đến 11:00 sáng thứ Bảy."),
            (user_2, "Hóa đơn tháng mới", "Hóa đơn tháng này đã sẵn sàng trên cổng người thuê."),
        ]
        for recipient, title, content in data:
            Notification.objects.get_or_create(recipient=recipient, title=title, defaults={"content": content})
