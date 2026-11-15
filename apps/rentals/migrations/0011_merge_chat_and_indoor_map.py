from django.db import migrations


class Migration(migrations.Migration):
    """Join the independently deployed chat and indoor-map migration branches."""

    dependencies = [
        ("rentals", "0009_chat_images"),
        ("rentals", "0010_camera_exitpoint_hazardzone_alertevent_mapzone_and_more"),
    ]

    operations = []
