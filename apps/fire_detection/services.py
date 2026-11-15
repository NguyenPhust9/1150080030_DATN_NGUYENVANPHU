import math
import os
import uuid
from decimal import Decimal

from django.db import transaction

from apps.rentals.models import AlertEvent, Camera, HazardZone


def record_camera_alert(detections, image_url):
    """Persist a confirmed webcam alert only when a camera is explicitly mapped."""
    valid_detections = []
    for detection in detections or ():
        try:
            confidence = float(detection.get("confidence", 0))
        except (ValueError, TypeError):
            continue
        if (detection.get("label") in {"fire", "smoke"}
                and math.isfinite(confidence) and 0 < confidence <= 1):
            valid_detections.append({**detection, "confidence": confidence})
    if not valid_detections:
        return None
    camera_id = os.getenv("FIRE_CAMERA_ID", "").strip()
    if not camera_id:
        return None
    try:
        parsed_id = uuid.UUID(camera_id)
    except ValueError:
        return None
    return _persist_camera_alert(parsed_id, valid_detections, image_url)


@transaction.atomic
def _persist_camera_alert(camera_id, detections, image_url):
    camera = Camera.objects.select_related("zone").filter(pk=camera_id, is_active=True).first()
    if camera is None:
        return None
    labels = {item.get("label") for item in detections}
    label = "fire" if "fire" in labels else "smoke"
    confidence = max(item["confidence"] for item in detections if item["label"] == label)
    hazard = None
    if camera.zone_id:
        hazard, _ = HazardZone.objects.get_or_create(
            indoor_map=camera.indoor_map,
            zone=camera.zone,
            camera=camera,
            is_active=True,
            is_simulation=False,
            defaults={"note": "Tạo tự động từ webcam sau khi xác nhận nhiều khung hình."},
        )
    return AlertEvent.objects.create(
        camera=camera,
        hazard=hazard,
        label=label,
        confidence=Decimal(str(confidence)),
        image_url=image_url,
    )
