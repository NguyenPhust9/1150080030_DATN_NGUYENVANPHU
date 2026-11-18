"""Serve management UI fixtures in shared-memory SQLite; never opens production DB.

Run: .venv/Scripts/python.exe -X utf8 tests/serve_admin_preview.py
URL: http://127.0.0.1:8005/quan-ly/
Users: admin-preview, owner-preview, staff-preview, tenant-preview
Password for all fixture users: local-preview-only
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_indoor_settings"

import django
from django.conf import settings
from django.core.management import call_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8005)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid port")
    settings.DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "file:admin-design-preview?mode=memory&cache=shared",
        "OPTIONS": {"uri": True},
    }}
    settings.DEBUG = True
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False
    settings.SECURE_SSL_REDIRECT = False
    references = {f"A10{i}": REPO_ROOT / "images" / "Anhphongtro" / f"A10{i}" for i in range(1, 6)}
    for number, directory in references.items():
        if directory.is_dir():
            settings.STATICFILES_DIRS = [*settings.STATICFILES_DIRS, (f"admin-reference-{number}", directory)]
    django.setup()

    from django.contrib.auth import get_user_model
    from django.db import connections
    from django.utils import timezone
    from apps.rentals.models import (
        Amenity, Building, Contract, ContractMember, ContractService, Incident,
        Invoice, InvoiceItem, MeterReading, Notification, Payment, Room, RoomMedia,
        Service, Tenant,
    )

    try:
        call_command("migrate", verbosity=0)
        User = get_user_model()
        users = {}
        for role, name in (("admin", "Nguyễn Văn Phú"), ("owner", "Trần Thanh An"), ("staff", "Lê Thu Hà"), ("tenant", "Phạm Minh Anh")):
            users[role] = User.objects.create_user(
                f"{role}-preview", password="local-preview-only", role=role,
                first_name=name, email=f"{role}@example.invalid",
                is_staff=role == "admin", is_superuser=role == "admin",
            )
        users["staff"].managed_owner = users["owner"]
        users["staff"].save(update_fields=["managed_owner"])
        amenities = [Amenity.objects.create(name=name) for name in ("Máy lạnh", "Wi-Fi", "Gác lửng", "Bếp riêng")]
        rooms = []
        building_data = (
            ("An Tâm", "118 Nguyễn Thị Minh Khai, Quận 3, TP.HCM"),
            ("Bình An", "25 Nguyễn Gia Trí, Bình Thạnh, TP.HCM"),
            ("Cát Tường", "42 Linh Trung, TP. Thủ Đức, TP.HCM"),
            ("Duyên Hải", "86 Bến Vân Đồn, Quận 4, TP.HCM"),
            ("Eden", "55 Phan Văn Trị, Gò Vấp, TP.HCM"),
        )
        for index, (name, address) in enumerate(building_data, 1):
            building = Building.objects.create(id=UUID(int=index), name=f"Tòa nhà {name}", address=address, owner=users["owner"])
            building.staff.add(users["staff"])
            for position in range(1, 6):
                number = f"{chr(64 + index)}10{position}"
                room = Room.objects.create(
                    id=UUID(int=index * 1000 + position), building=building,
                    number=number, floor=1, area=20 + position,
                    monthly_rent=2700000 + index * 100000 + position * 50000,
                    deposit_amount=3000000, max_occupants=2,
                    status="occupied" if position <= 2 else "available",
                    description="Phòng có gác lửng, khu bếp riêng và cửa sổ thoáng.",
                )
                room.amenities.set(amenities)
                rooms.append(room)
                directory = references.get(number)
                if directory and directory.is_dir():
                    primary = True
                    for source in sorted(directory.iterdir()):
                        suffix = source.suffix.lower()
                        kind = "image" if suffix in {".jpg", ".jpeg", ".png", ".webp"} else "video" if suffix in {".mp4", ".webm", ".mov"} else None
                        if not source.is_file() or not kind:
                            continue
                        RoomMedia.objects.create(
                            room=room, media_type=kind,
                            url=f"http://127.0.0.1:{args.port}/static/admin-reference-{number}/{quote(source.name)}",
                            public_id=f"local-preview/{number}/{source.name}", format=suffix[1:],
                            is_primary=primary and kind == "image",
                        )
                        if kind == "image":
                            primary = False
        electricity = Service.objects.create(owner=users["owner"], name="Điện", unit="kwh", unit_price=3500, is_metered=True)
        water = Service.objects.create(owner=users["owner"], name="Nước", unit="m3", unit_price=18000, is_metered=True)
        internet = Service.objects.create(owner=users["owner"], name="Internet", unit="room", unit_price=100000)
        today = timezone.localdate()
        occupied = [room for room in rooms if room.status == "occupied"]
        for index, room in enumerate(occupied, 1):
            tenant = Tenant.objects.create(
                id=UUID(int=20000 + index), owner=users["owner"],
                user=users["tenant"] if index == 1 else None,
                full_name=("Phạm Minh Anh", "Nguyễn Hoàng Nam", "Trần Ngọc Mai", "Lê Gia Bảo", "Võ Thu Thảo")[((index - 1) % 5)],
                phone=f"090000{index:04d}", email=f"tenant{index}@example.invalid",
            )
            contract = Contract.objects.create(
                id=UUID(int=30000 + index), code=f"HD-{room.number}-2026",
                room=room, representative=tenant, start_date=today - timedelta(days=180),
                end_date=today + timedelta(days=7 * index), monthly_rent=room.monthly_rent,
                deposit_amount=room.deposit_amount, status="active",
            )
            ContractMember.objects.create(contract=contract, tenant=tenant, joined_date=contract.start_date)
            ContractService.objects.create(contract=contract, service=internet, unit_price=internet.unit_price)
            for ago in range(5, -1, -1):
                month_index = today.year * 12 + today.month - 1 - ago
                year, month = divmod(month_index, 12)
                period = date(year, month + 1, 1)
                total = int(room.monthly_rent) + 280000 + index * 15000
                paid = total if ago > 0 or index % 3 == 0 else 1500000 if index % 3 == 1 else 0
                status = "paid" if paid == total else "partial" if paid else "overdue"
                invoice = Invoice.objects.create(
                    id=UUID(int=40000 + index * 100 + ago), code=f"HDON-{period:%m%y}-{room.number}",
                    contract=contract, period=period, issued_date=period,
                    due_date=period + timedelta(days=5), subtotal=total,
                    total_amount=total, paid_amount=paid, status=status,
                )
                InvoiceItem.objects.create(invoice=invoice, description="Tiền thuê phòng", quantity=1, unit_price=room.monthly_rent)
                InvoiceItem.objects.create(invoice=invoice, description="Điện, nước và Internet", quantity=1, unit_price=total - int(room.monthly_rent))
                if paid:
                    paid_at = timezone.make_aware(timezone.datetime.combine(period + timedelta(days=3), timezone.datetime.min.time()))
                    Payment.objects.create(invoice=invoice, amount=paid, paid_at=paid_at, method="transfer", received_by=users["owner"], reference=f"PREVIEW-{index}-{ago}")
            for meter_type, previous, current in (("electricity", 100, 145), ("water", 20, 24)):
                MeterReading.objects.create(room=room, meter_type=meter_type, period=today.replace(day=1), previous_value=previous, current_value=current, recorded_by=users["staff"])
            if index <= 3:
                Incident.objects.create(room=room, reported_by=tenant, title=("Vòi nước bị rò rỉ", "Kiểm tra ổ điện khu bếp", "Đèn hành lang cần thay")[index - 1], description="Nhờ ban quản lý kiểm tra trong giờ hành chính.", priority="high" if index == 2 else "medium", assigned_to=users["staff"])
        for recipient in users.values():
            Notification.objects.create(title="Lịch kiểm tra điện nước", content="Ban quản lý kiểm tra định kỳ vào sáng thứ bảy.", recipient=recipient, created_by=users["owner"])
        print(f"Admin preview: http://127.0.0.1:{args.port}/quan-ly/", flush=True)
        print("Users: admin-preview / owner-preview / staff-preview / tenant-preview", flush=True)
        print("Password: local-preview-only (isolated fixture only)", flush=True)
        call_command("runserver", f"127.0.0.1:{args.port}", use_reloader=False)
    finally:
        connections.close_all()


if __name__ == "__main__":
    main()
