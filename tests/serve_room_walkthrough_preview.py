"""Local A101/A102/A103/A104/A105 UI fixture; database data lives in process memory.

Run: .venv/Scripts/python.exe tests/serve_room_walkthrough_preview.py
Login: walkthrough-preview / local-preview-only
URL: http://127.0.0.1:8003/phong/a1010000-0000-4000-8000-000000000001/tham-quan/
URL: http://127.0.0.1:8003/phong/a1020000-0000-4000-8000-000000000002/tham-quan/
URL: http://127.0.0.1:8003/phong/a1030000-0000-4000-8000-000000000003/tham-quan/
URL: http://127.0.0.1:8003/phong/a1040000-0000-4000-8000-000000000004/tham-quan/
URL: http://127.0.0.1:8003/phong/a1050000-0000-4000-8000-000000000005/tham-quan/

Optional images/Anhphongtro/A101-A105 files are served without uploading.
The configured application database is never opened or modified.
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOM_ID = "a1010000-0000-4000-8000-000000000001"
ROOM_IDS = {
    "A101": ROOM_ID,
    "A102": "a1020000-0000-4000-8000-000000000002",
    "A103": "a1030000-0000-4000-8000-000000000003",
    "A104": "a1040000-0000-4000-8000-000000000004",
    "A105": "a1050000-0000-4000-8000-000000000005",
}
sys.path.insert(0, str(REPO_ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_indoor_settings"

import django
from django.conf import settings
from django.core.management import call_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    # A named, shared memory database lets Django's request threads read the
    # fixture created by this main thread. It cannot reach PostgreSQL.
    settings.DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": "file:room-walkthrough-preview?mode=memory&cache=shared",
            "OPTIONS": {"uri": True},
        }
    }
    settings.DEBUG = True
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False
    settings.SECURE_SSL_REDIRECT = False
    reference_dirs = {
        number: REPO_ROOT / "images" / "Anhphongtro" / number
        for number in ROOM_IDS
    }
    for number, reference_dir in reference_dirs.items():
        if not reference_dir.is_dir():
            continue
        settings.STATICFILES_DIRS = [
            *settings.STATICFILES_DIRS,
            (f"walkthrough-reference-{number}", reference_dir),
        ]
    django.setup()

    from django.contrib.auth import get_user_model
    from django.db import connections
    from apps.rentals.models import Building, Room, RoomMedia

    try:
        call_command("migrate", verbosity=0)
        owner = get_user_model().objects.create_user(
            "walkthrough-preview", password="local-preview-only", role="owner",
        )
        building = Building.objects.create(
            name="Tòa nhà An Tâm", address="Dữ liệu kiểm thử cục bộ", owner=owner,
        )
        for number, room_id in ROOM_IDS.items():
            room = Room.objects.create(
                id=room_id, building=building, number=number, floor=1,
                area=25, monthly_rent=3200000,
            )
            reference_dir = reference_dirs[number]
            if not reference_dir.is_dir():
                continue
            for source in sorted(reference_dir.iterdir()):
                if not source.is_file():
                    continue
                suffix = source.suffix.lower()
                if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
                    media_type = RoomMedia.MediaType.IMAGE
                elif suffix in {".mp4", ".webm", ".mov"}:
                    media_type = RoomMedia.MediaType.VIDEO
                else:
                    continue
                RoomMedia.objects.create(
                    room=room, media_type=media_type,
                    url=f"http://127.0.0.1:{args.port}/static/walkthrough-reference-{number}/{quote(source.name)}",
                    public_id=f"local-preview/{number}/{source.name}", format=suffix[1:],
                )
        for number, room_id in ROOM_IDS.items():
            print(f"{number}: http://127.0.0.1:{args.port}/phong/{room_id}/tham-quan/", flush=True)
        print("Login: walkthrough-preview / local-preview-only", flush=True)
        call_command("runserver", f"127.0.0.1:{args.port}", use_reloader=False)
    finally:
        connections.close_all()


if __name__ == "__main__":
    main()
