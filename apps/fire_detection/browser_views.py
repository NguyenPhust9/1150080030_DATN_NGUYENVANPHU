import hashlib
import io
import logging
import os
import time
import uuid
import warnings
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from PIL import Image, ImageDraw, UnidentifiedImageError

from apps.rentals.models import Camera
from apps.rentals.permissions import get_accessible_buildings, require_operator

from .inference import DetectorConfig, TemporalConfirmation
from .models import BrowserFireAlert
from .onnx_inference import predict_image
from .services import record_camera_alert
from .webhook import post_alert_webhook, upload_alert_image

logger = logging.getLogger(__name__)


def config_payload():
    config = DetectorConfig.from_environment(settings.BASE_DIR)
    return {"image_size": 512, "fire_confidence": config.fire_confidence,
            "smoke_confidence": config.smoke_confidence, "confirm_frames": config.confirm_frames,
            "confirmation_window": config.confirmation_window, "model_source": "YOLO lửa/khói · ONNX 512 px"}


def read_frame(request):
    image = request.FILES.get("image")
    if not image or image.size > 1024 * 1024:
        raise ValueError("Khung hình phải nhỏ hơn 1 MB.")
    raw = image.read()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            decoded = Image.open(io.BytesIO(raw))
            if decoded.format != "JPEG" or decoded.width * decoded.height > 2_100_000:
                raise ValueError("Khung hình phải là JPEG tối đa 2 megapixel.")
            decoded.load()
            return raw, decoded.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Khung hình không hợp lệ.") from exc


@login_required
@require_GET
def browser_config(request):
    require_operator(request.user)
    cutoff = timezone.now() - timedelta(minutes=2)
    BrowserFireAlert.objects.filter(user=request.user, created_at__lt=cutoff, delivery_state="pending").update(delivery_state="expired")
    BrowserFireAlert.objects.filter(user=request.user, created_at__lt=cutoff, delivery_state="sending").update(delivery_state="unknown")
    events = [{"id": str(item.pk), "time": timezone.localtime(item.created_at).strftime("%H:%M:%S %d/%m/%Y"),
               "labels": sorted({d["label"] for d in item.detections}), "image_url": item.image_url,
               "webhook_state": item.delivery_state, "persistence_state": item.persistence_state}
              for item in BrowserFireAlert.objects.filter(user=request.user).order_by("-created_at")[:10]]
    return JsonResponse({**config_payload(), "events": events})


@login_required
@require_POST
def browser_start(request):
    require_operator(request.user)
    run_id = uuid.uuid4().hex
    request.session["fire_browser"] = {"run_id": run_id, "sequence": 0, "window": [], "last_seen": 0}
    return JsonResponse({"run_id": run_id, **config_payload()})


@login_required
@require_POST
def browser_stop(request):
    require_operator(request.user)
    monitor = request.session.get("fire_browser", {})
    if monitor.get("run_id") == request.POST.get("run_id"):
        request.session.pop("fire_browser", None)
    return JsonResponse({"ok": True})


def reserve_alert(user, detections, raw):
    config = DetectorConfig.from_environment(settings.BASE_DIR)
    with transaction.atomic():
        get_user_model().objects.select_for_update().only("id").get(pk=user.pk)
        if BrowserFireAlert.objects.filter(user=user, created_at__gte=timezone.now() - timedelta(seconds=config.cooldown_seconds)).exists():
            return None
        return BrowserFireAlert.objects.create(user=user, detections=detections, image_sha256=hashlib.sha256(raw).hexdigest())


@login_required
@require_POST
def browser_frame(request):
    require_operator(request.user)
    monitor = request.session.get("fire_browser", {})
    try:
        sequence = int(request.POST.get("sequence", "0"))
        if not monitor or monitor.get("run_id") != request.POST.get("run_id") or sequence <= monitor.get("sequence", 0):
            return JsonResponse({"message": "Phiên camera đã đổi. Hãy dừng và bắt đầu lại."}, status=409)
        raw, image = read_frame(request)
    except (ValueError, TypeError) as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    tick = time.monotonic()
    try:
        detections = predict_image(image)
    except Exception as exc:
        logger.error("Browser frame inference failed (%s)", type(exc).__name__)
        return JsonResponse({"message": "Chưa xử lý được khung hình AI. Hãy thử lại sau."}, status=503)
    config = DetectorConfig.from_environment(settings.BASE_DIR)
    tracker = TemporalConfirmation(config.confirm_frames, config.confirmation_window)
    if time.time() - monitor.get("last_seen", 0) <= 10:
        for previous in monitor.get("window", [])[-(config.confirmation_window - 1):]:
            tracker.window.append(tuple(previous))
    state, evidence = tracker.update(detections)
    monitor.update(sequence=sequence, window=list(tracker.window), last_seen=time.time())
    request.session["fire_browser"] = monitor
    labels = {item["label"] for item in evidence}
    current = [item for item in detections if item["label"] in labels]
    alert = reserve_alert(request.user, current, raw) if state == "alert" and current else None
    return JsonResponse({"state": state, "detections": detections, "width": image.width, "height": image.height,
                         "inference_ms": round((time.monotonic() - tick) * 1000),
                         "alert": {"id": str(alert.pk), "time": timezone.localtime(alert.created_at).strftime("%H:%M:%S %d/%m/%Y"),
                                   "labels": sorted(labels)} if alert else None})


@login_required
@require_POST
def browser_deliver(request, alert_id):
    require_operator(request.user)
    alert = BrowserFireAlert.objects.filter(pk=alert_id, user=request.user).first()
    if alert is None:
        return JsonResponse({"message": "Không tìm thấy cảnh báo."}, status=404)
    try:
        raw, image = read_frame(request)
    except ValueError as exc:
        return JsonResponse({"message": str(exc)}, status=400)
    if hashlib.sha256(raw).hexdigest() != alert.image_sha256:
        return JsonResponse({"message": "Ảnh không khớp khung hình đã xác nhận."}, status=400)
    with transaction.atomic():
        alert = BrowserFireAlert.objects.select_for_update().get(pk=alert.pk)
        if alert.delivery_state != "pending":
            return JsonResponse({"webhook_state": alert.delivery_state, "image_url": alert.image_url,
                                 "persistence_state": alert.persistence_state})
        if timezone.now() - alert.created_at > timedelta(minutes=2):
            alert.delivery_state = "expired"
            alert.save(update_fields=["delivery_state"])
            return JsonResponse({"webhook_state": "expired", "image_url": ""})
        alert.delivery_state = "sending"
        alert.save(update_fields=["delivery_state"])
    event = {"id": str(alert.pk), "detected_at": alert.created_at.isoformat()}
    drawing = ImageDraw.Draw(image)
    for detection in alert.detections:
        box = detection["xyxy"]
        drawing.rectangle(box, outline="red" if detection["label"] == "fire" else "orange", width=3)
        drawing.text((box[0], max(0, box[1] - 14)), f"{detection['label']} {detection['confidence']:.2f}", fill="red")
    image_file = io.BytesIO()
    image.save(image_file, format="JPEG", quality=85)
    image_file.seek(0)
    stage = "cloudinary"
    try:
        alert.image_url = upload_alert_image(event, image_file)
        alert.save(update_fields=["image_url"])
        try:
            camera_id = os.getenv("FIRE_CAMERA_ID", "")
            allowed = bool(camera_id) and Camera.objects.filter(
                pk=camera_id, indoor_map__building__in=get_accessible_buildings(request.user)).exists()
            saved = record_camera_alert(alert.detections, alert.image_url) if allowed else None
            alert.persistence_state = "saved" if saved else "unmapped"
        except Exception:
            alert.persistence_state = "failed"
        alert.save(update_fields=["persistence_state"])
        if os.getenv("FIRE_WEBHOOK_URL", "").strip():
            stage = "webhook"
            post_alert_webhook(event, alert.detections, alert.image_url)
            alert.delivery_state = "sent"
        else:
            alert.delivery_state = "disabled"
    except Exception as exc:
        logger.warning("Browser alert delivery failed at %s (%s), event %s", stage, type(exc).__name__, alert.pk)
        alert.delivery_state = "failed"
    alert.save(update_fields=["delivery_state"])
    return JsonResponse({"webhook_state": alert.delivery_state, "image_url": alert.image_url,
                         "persistence_state": alert.persistence_state})
