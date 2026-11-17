"""Serve a realistic public-home fixture using an isolated in-memory database.

Run: .venv/Scripts/python.exe tests/serve_public_home_preview.py
URL: http://127.0.0.1:8005/
Optional local A101-A104 reference media is served directly; nothing is uploaded.
The application database is never opened or modified.
"""

import argparse
import os
import sys
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
        parser.error("--port must be between 1 and 65535")

    settings.DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": "file:public-home-preview?mode=memory&cache=shared",
            "OPTIONS": {"uri": True},
        }
    }
    settings.DEBUG = True
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False
    settings.SECURE_SSL_REDIRECT = False
    references = {
        number: REPO_ROOT / "images" / "Anhphongtro" / number
        for number in ("A101", "A102", "A103", "A104")
    }
    for number, directory in references.items():
        if directory.is_dir():
            settings.STATICFILES_DIRS = [
                *settings.STATICFILES_DIRS,
                (f"home-reference-{number}", directory),
            ]
    django.setup()

    from django.contrib.auth import get_user_model
    from django.db import connections
    from apps.rentals.models import Amenity, Building, Room, RoomMedia

    try:
        call_command("migrate", verbosity=0)
        owner = get_user_model().objects.create_user(
            "home-preview", password="local-preview-only", role="owner",
            first_name="Phú", email="preview@example.invalid",
        )
        amenities = {
            name: Amenity.objects.create(name=name)
            for name in ("Máy lạnh", "Bãi xe", "Wi-Fi", "Gác lửng", "Bếp riêng")
        }
        buildings = (
            ("A", "Tòa nhà An Tâm", "118 Nguyễn Thị Minh Khai, Quận 3, TP.HCM", 12),
            ("B", "Tòa nhà Bình An", "25 Nguyễn Gia Trí, Bình Thạnh, TP.HCM", 8),
            ("C", "Tòa nhà Cát Tường", "36 Hoàng Diệu, Quận 4, TP.HCM", 5),
            ("D", "Tòa nhà Duyên Hải", "17 Võ Văn Ngân, Thủ Đức, TP.HCM", 5),
            ("E", "Tòa nhà Eden", "80 Nguyễn Văn Lượng, Gò Vấp, TP.HCM", 5),
        )
        for index, (prefix, name, address, count) in enumerate(buildings, start=1):
            building = Building.objects.create(
                id=UUID(int=index), name=name, address=address, owner=owner,
            )
            for number in range(1, count + 1):
                floor, position = divmod(number - 1, 5)
                room_number = f"{prefix}{floor + 1}{position + 1:02d}"
                room = Room.objects.create(
                    id=UUID(int=1000 * index + number), building=building,
                    number=room_number, floor=floor + 1, area=20 + number,
                    monthly_rent=2500000 + index * 100000 + number * 100000,
                    max_occupants=2 if number % 3 else 3,
                    description="Phòng có cửa sổ, bếp riêng và không gian sinh hoạt thoáng.",
                )
                room.amenities.add(amenities["Wi-Fi"], amenities["Bếp riêng"])
                if number % 2 == 0:
                    room.amenities.add(amenities["Máy lạnh"], amenities["Bãi xe"])
                if number <= 4:
                    room.amenities.add(amenities["Gác lửng"])
                directory = references.get(room_number)
                if directory is None or not directory.is_dir():
                    continue
                first_image = True
                for source in sorted(directory.iterdir()):
                    if not source.is_file():
                        continue
                    suffix = source.suffix.lower()
                    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
                        media_type = RoomMedia.MediaType.IMAGE
                    elif suffix in {".mp4", ".webm", ".mov"}:
                        media_type = RoomMedia.MediaType.VIDEO
                    else:
                        continue
                    primary = first_image and media_type == RoomMedia.MediaType.IMAGE
                    RoomMedia.objects.create(
                        room=room, media_type=media_type, is_primary=primary,
                        url=f"http://127.0.0.1:{args.port}/static/home-reference-{room_number}/{quote(source.name)}",
                        public_id=f"local-preview/{room_number}/{source.name}",
                        format=suffix[1:],
                    )
                    if primary:
                        first_image = False
            # Unavailable rooms must never leak into the public room list/count.
            Room.objects.create(
                building=building, number=f"{prefix}401", floor=4,
                area=24, monthly_rent=3100000, status=Room.Status.OCCUPIED,
            )
        print(f"Public home: http://127.0.0.1:{args.port}/", flush=True)
        print("Fixture: 5 buildings / 35 available rooms / A101-A104 optional local media", flush=True)
        call_command("runserver", f"127.0.0.1:{args.port}", use_reloader=False)
    finally:
        connections.close_all()


if __name__ == "__main__":
    main()
