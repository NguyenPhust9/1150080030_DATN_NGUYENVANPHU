"""Send confirmed alert evidence to n8n without blocking camera inference."""
import json
import os
import queue
import threading
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import cloudinary.uploader

WEBHOOK_ERROR = "Chưa xác nhận được n8n đã nhận cảnh báo. Kiểm tra workflow và kết nối."


def webhook_target():
    target = os.getenv("FIRE_WEBHOOK_URL", "").strip()
    endpoint = urlparse(target)
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
        raise ValueError("FIRE_WEBHOOK_URL must be an HTTPS webhook URL")
    return target


def upload_alert_image(event, image):
    parsed = urlparse(os.getenv("CLOUDINARY_URL", ""))
    credentials = {
        "cloud_name": os.getenv("CLOUDINARY_CLOUD_NAME") or parsed.hostname,
        "api_key": os.getenv("CLOUDINARY_API_KEY") or unquote(parsed.username or ""),
        "api_secret": os.getenv("CLOUDINARY_API_SECRET") or unquote(parsed.password or ""),
    }
    if not all(credentials.values()):
        raise ValueError("Cloudinary is not configured")
    result = cloudinary.uploader.upload(
        image, **credentials, resource_type="image", type="upload",
        public_id=f"ql-phong-cho-thue/fire-alerts/{event['id']}",
        overwrite=False, timeout=20,
    )
    image_url = result["secure_url"]
    uploaded = urlparse(image_url)
    if uploaded.scheme != "https" or uploaded.hostname != "res.cloudinary.com" or len(image_url) > 500:
        raise ValueError("Cloudinary did not return a valid HTTPS image URL")
    return image_url


def post_alert_webhook(event, detections, image_url):
    label = "fire" if any(d["label"] == "fire" for d in detections) else "smoke"
    payload = {
        "event_id": event["id"], "detected_at": event["detected_at"],
        "camera_id": os.getenv("FIRE_CAMERA_ID", ""),
        "camera_name": os.getenv("FIRE_CAMERA_NAME", "").strip() or "Webcam " + os.getenv("FIRE_CAMERA_INDEX", "0"),
        "location": os.getenv("FIRE_CAMERA_LOCATION", ""), "label": label,
        "confidence": max(float(d["confidence"]) for d in detections if d["label"] == label),
        "detections": list(detections), "image_url": image_url,
    }
    headers = {"Content-Type": "application/json", "Idempotency-Key": event["id"]}
    token = os.getenv("FIRE_WEBHOOK_TOKEN", "").strip()
    if token:
        headers["X-Fire-Webhook-Token"] = token
    request = Request(webhook_target(), data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urlopen(request, timeout=15) as response:
        if not 200 <= response.status < 300:
            raise ValueError("Webhook rejected the event")


def deliver_fire_alert(event, detections, image_path):
    webhook_target()
    with open(image_path, "rb") as image:
        image_url = upload_alert_image(event, image)
    post_alert_webhook(event, detections, image_url)
    return image_url


class AlertWebhookWorker:
    """One worker, bounded in-memory queue; pending work is lost on process exit."""

    def __init__(self, on_update, capacity=8, deliver=None):
        self._queue = queue.Queue(maxsize=capacity)
        self._on_update = on_update
        self._deliver = deliver or deliver_fire_alert
        self._lock = threading.Lock()
        self._thread = None
        self._closing = threading.Event()
        self._active = False
        self._failed = 0

    @property
    def enabled(self):
        return bool(os.getenv("FIRE_WEBHOOK_URL", "").strip())

    def submit(self, event, detections, image_path):
        task = (dict(event), tuple(dict(d) for d in detections), str(image_path))
        with self._lock:
            if self._closing.is_set():
                return False
            try:
                self._queue.put_nowait(task)
            except queue.Full:
                self._failed += 1
                return False
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="fire-alert-webhook", daemon=True)
                try:
                    self._thread.start()
                except Exception:
                    self._thread = None
                    self._queue.get_nowait()
                    self._queue.task_done()
                    self._failed += 1
                    raise
        return True

    def snapshot(self):
        with self._lock:
            return {"enabled": self.enabled, "pending": self._queue.qsize(),
                    "active": self._active, "failed": self._failed}

    def close(self, timeout=0.5):
        self._closing.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def _notify(self, event_id, state, error="", image_url=""):
        try:
            self._on_update(event_id, state, error, image_url)
        except Exception:
            # UI failures must not terminate notification delivery for later events.
            pass

    def _run(self):
        while True:
            try:
                event, detections, image_path = self._queue.get(timeout=0.2)
            except queue.Empty:
                if self._closing.is_set():
                    return
                continue
            with self._lock:
                self._active = True
            self._notify(event["id"], "sending")
            try:
                image_url = self._deliver(event, detections, image_path)
            except Exception:
                with self._lock:
                    self._failed += 1
                self._notify(event["id"], "failed", WEBHOOK_ERROR)
            else:
                self._notify(event["id"], "sent", image_url=image_url)
            finally:
                with self._lock:
                    self._active = False
                self._queue.task_done()
