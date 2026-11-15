"""Local-only UI fixture. Uses a temporary SQLite DB, never the configured DB.

Run: .venv/Scripts/python.exe tests/serve_indoor_preview.py
Then: node tests/indoor_map_browser.mjs
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_indoor_settings"

import django
from django.conf import settings
from django.core.management import call_command


def main():
    with tempfile.TemporaryDirectory(prefix="indoor-preview-") as directory:
        settings.DATABASES["default"]["NAME"] = str(Path(directory) / "preview.sqlite3")
        django.setup()
        from django.contrib.auth import get_user_model
        from django.db import connections
        from apps.rentals.models import Building, IndoorMap, Room

        call_command("migrate", verbosity=0)
        owner = get_user_model().objects.create_user("indoor-preview", password="local-preview-only", role="owner")
        building = Building.objects.create(name="Tòa nhà mẫu", address="Dữ liệu kiểm thử", owner=owner)
        for number in ("A01", "F1-01", "F1-02", "F1-03", "F1-04"):
            Room.objects.create(building=building, number=number, floor=1, monthly_rent=3200000)
        call_command("seed_indoor_map", building_id=str(building.id))
        indoor = IndoorMap.objects.get(building=building)
        call_command("build_demo_floorplan", map_id=str(indoor.id), backup_dir=directory)
        try:
            call_command("runserver", "127.0.0.1:8001", use_reloader=False)
        finally:
            connections.close_all()


if __name__ == "__main__":
    main()
