import asyncio
import logging
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

from django.conf import settings

from .inference import DetectorConfig, TemporalConfirmation, filter_detections, validate_model_classes
from .persistence import PERSISTENCE_ERROR, QUEUE_FULL_ERROR, AlertPersistenceWorker
from .webhook import WEBHOOK_ERROR, AlertWebhookWorker

logger = logging.getLogger(__name__)
STATE_LABELS = {
    "stopped": "Đã dừng giám sát",
    "starting": "Đang khởi động camera và AI…",
    "stopping": "Đang dừng camera…",
    "monitoring": "Chưa phát hiện lửa/khói",
    "detecting": "Đang xác minh dấu hiệu lửa/khói…",
    "alert": "Cảnh báo phát hiện lửa/khói",
    "error": "Không thể giám sát",
}


class WebcamFireDetector:
    def __init__(self):
        self._lock = threading.RLock()
        self._thread = None
        self._stop_event = threading.Event()
        self._active_config = None
        self._frame = None
        self._frame_sequence = 0
        self._last_frame_at = None
        self._last_frame_tick = None
        self._running = False
        self._loading = False
        self._error = ""
        self._state = "stopped"
        self._detections = []
        self._alert_labels = []
        self._events = deque(maxlen=10)
        self._persistence = AlertPersistenceWorker(self._update_event_persistence)
        self._webhook = AlertWebhookWorker(self._update_event_webhook)
        self._last_alert_at = None
        self._confirmation = TemporalConfirmation()
        self._fps = 0.0

    @property
    def model_path(self):
        with self._lock:
            config = self._active_config or DetectorConfig.from_environment(settings.BASE_DIR)
            return config.model_path

    def _clear_result(self):
        """Caller holds the lock. Old frames never survive a failed/restarted run."""
        self._frame = None
        self._last_frame_at = None
        self._last_frame_tick = None
        self._detections = []
        self._alert_labels = []
        self._fps = 0.0
        self._confirmation.clear()

    def start(self):
        if os.getenv("VERCEL"):
            return False, "Webcam cần chạy trên máy có camera. Hãy mở trang giám sát trên Django local; Vercel không có webcam."
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self._stop_event.is_set():
                    return False, "Camera đang dừng. Hãy chờ trước khi khởi động lại."
                return True, "Camera đang hoạt động hoặc đang khởi động."
            self._clear_result()
            self._error = ""
            try:
                config = DetectorConfig.from_environment(settings.BASE_DIR)
                if not config.model_path.is_file():
                    raise ValueError(f"Không tìm thấy mô hình: {config.model_path}")
            except (ValueError, OSError) as exc:
                self._error = str(exc)
                self._state = "error"
                self._running = self._loading = False
                return False, self._error
            self._active_config = config
            self._confirmation = TemporalConfirmation(config.confirm_frames, config.confirmation_window)
            self._last_alert_at = None
            # A stopped worker can never be revived by clearing its old event.
            self._stop_event = threading.Event()
            self._running = False
            self._loading = True
            self._state = "starting"
            self._thread = threading.Thread(
                target=self._run, args=(config, self._stop_event), name="fire-webcam", daemon=True
            )
            self._thread.start()
        return True, "Đang khởi động camera và mô hình AI."

    def stop(self):
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            self._running = self._loading = False
            self._state = "stopping" if thread and thread.is_alive() else "stopped"
            self._clear_result()
        if thread and thread.is_alive():
            thread.join(timeout=3)
        with self._lock:
            if thread is self._thread and (thread is None or not thread.is_alive()):
                self._state = "stopped"

    def snapshot(self):
        with self._lock:
            configuration_error = ""
            try:
                config = self._active_config or DetectorConfig.from_environment(settings.BASE_DIR)
            except (ValueError, OSError) as exc:
                configuration_error = str(exc)
                config = DetectorConfig.from_environment(settings.BASE_DIR, {})
            age = (max(0.0, time.monotonic() - self._last_frame_tick)
                   if self._last_frame_tick is not None else None)
            try:
                source = config.model_path.relative_to(settings.BASE_DIR).as_posix()
            except ValueError:
                source = config.model_path.as_posix()
            return {
                "running": self._running,
                "loading": self._loading,
                "state": self._state,
                "state_label": STATE_LABELS.get(self._state, self._state),
                "error": self._error or configuration_error,
                "fps": round(self._fps, 1),
                "detections": list(self._detections),
                "alert_labels": list(self._alert_labels),
                "events": [dict(event) for event in self._events],
                "persistence": self._persistence.snapshot(),
                "webhook": self._webhook.snapshot(),
                "model_name": config.model_path.name,
                "model_source": source,
                "model_run": (config.model_path.parent.parent.name
                              if config.model_path.parent.name == "weights" else config.model_path.parent.name),
                "configuration_source": "active" if self._active_config else "configured",
                "camera_index": config.camera_index,
                "image_size": config.image_size,
                "fire_confidence": config.fire_confidence,
                "smoke_confidence": config.smoke_confidence,
                "confirm_frames": config.confirm_frames,
                "confirmation_window": config.confirmation_window,
                "last_frame_at": self._last_frame_at,
                "frame_age_seconds": round(age, 2) if age is not None else None,
                "result_stale": age is None or age > config.stale_after_seconds,
            }

    async def mjpeg_frames(self):
        last_sequence = None
        while True:
            with self._lock:
                active = (self._running or self._loading) and not self._stop_event.is_set()
                frame, sequence = self._frame, self._frame_sequence
                fresh = (self._last_frame_tick is not None
                         and time.monotonic() - self._last_frame_tick <= 10)
            if not active:
                break
            if frame and fresh and sequence != last_sequence:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                last_sequence = sequence
            await asyncio.sleep(0.05)

    def _run(self, config, stop_event):
        capture = None
        try:
            import cv2
            from ultralytics import YOLO

            model = YOLO(str(config.model_path))
            if stop_event.is_set():
                return
            validate_model_classes(model.names)
            capture = cv2.VideoCapture(config.camera_index, cv2.CAP_DSHOW)
            if not capture.isOpened():
                capture.release()
                capture = cv2.VideoCapture(config.camera_index)
            if not capture.isOpened():
                raise RuntimeError(
                    f"Không mở được webcam số {config.camera_index}. Hãy đóng ứng dụng khác đang dùng camera."
                )
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            with self._lock:
                if stop_event.is_set():
                    return
                self._running = True
                self._loading = False
                # No reassuring status until the first successful inference.
                self._state = "starting"

            last_tick = time.monotonic()
            while not stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError("Mất kết nối với webcam.")
                if stop_event.is_set():
                    break
                result = model.predict(
                    frame, imgsz=config.image_size,
                    conf=min(config.fire_confidence, config.smoke_confidence),
                    iou=0.7, max_det=300, verbose=False
                )[0]
                detections = filter_detections(result, frame.shape, config)
                with self._lock:
                    if stop_event.is_set():
                        break
                    state, evidence = self._confirmation.update(detections)
                alert_labels = sorted({item["label"] for item in evidence})
                annotated = frame.copy()
                for detection in detections:
                    x1, y1, x2, y2 = detection["xyxy"]
                    label = detection["label"]
                    box_color = (0, 70, 255) if label == "fire" else (255, 170, 0)
                    caption = f"{label} {detection['confidence']:.2f}"
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)
                    cv2.putText(annotated, caption, (x1, max(22, y1 - 7)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, box_color, 2)
                color = (0, 0, 255) if state == "alert" else (
                    (0, 185, 255) if state == "detecting" else (220, 220, 220)
                )
                if state == "alert":
                    text = "CANH BAO LUA" if "fire" in alert_labels else "CANH BAO KHOI"
                else:
                    text = "DANG XAC MINH" if state == "detecting" else "CHUA PHAT HIEN LUA/KHOI"
                cv2.rectangle(annotated, (10, 10), (min(frame.shape[1] - 10, 475), 62),
                              (15, 20, 32), -1)
                cv2.putText(annotated, text, (24, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.72, color, 2)

                encoded, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
                if not encoded:
                    raise RuntimeError("Không thể mã hóa hình ảnh webcam.")
                now = time.monotonic()
                elapsed = max(now - last_tick, 0.001)
                last_tick = now
                with self._lock:
                    if stop_event.is_set():
                        break
                    self._frame = buffer.tobytes()
                    self._frame_sequence += 1
                    self._last_frame_at = datetime.now(timezone.utc).isoformat()
                    self._last_frame_tick = now
                    self._state = state
                    self._detections = detections
                    self._alert_labels = alert_labels
                    self._fps = 1.0 / elapsed

                # Confirmation can outlive a visible box. Save only actual current
                # evidence for a confirmed class, never an empty or mislabeled alert.
                current_evidence = [item for item in detections if item["label"] in alert_labels]
                if (state == "alert" and current_evidence and not stop_event.is_set()
                        and (self._last_alert_at is None
                             or now - self._last_alert_at >= config.cooldown_seconds)):
                    if self._save_event(annotated, current_evidence, cv2):
                        self._last_alert_at = now
        except Exception as exc:
            with self._lock:
                if not stop_event.is_set():
                    self._error = str(exc)
                    self._state = "error"
                self._clear_result()
            logger.exception("Webcam fire detector stopped")
        finally:
            if capture is not None:
                capture.release()
            with self._lock:
                self._running = self._loading = False
                if stop_event.is_set():
                    self._state = "stopped"
                    self._clear_result()

    def _update_event_persistence(self, event_id, state, error):
        with self._lock:
            for event in self._events:
                if event["id"] == event_id:
                    event["persistence_state"] = state
                    event["persistence_error"] = error
                    break

    def _update_event_webhook(self, event_id, state, error="", image_url=""):
        with self._lock:
            for event in self._events:
                if event["id"] == event_id:
                    event["webhook_state"] = state
                    event["webhook_error"] = error
                    if image_url:
                        event["webhook_image_url"] = image_url
                    break

    def _save_event(self, frame, detections, cv2):
        if not detections:
            return False
        event_dir = settings.MEDIA_ROOT / "fire_alerts"
        try:
            event_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"fire_alert_{stamp}.jpg"
            if not cv2.imwrite(str(event_dir / filename), frame):
                logger.warning("Could not save webcam alert image")
                return False
        except OSError:
            logger.exception("Could not save webcam alert image")
            return False
        labels = sorted({item["label"] for item in detections})
        event = {
            "id": uuid.uuid4().hex,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "webhook_state": "queued" if self._webhook.enabled else "disabled",
            "webhook_error": "",
            "time": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
            "labels": labels,
            "image_url": f"/{settings.MEDIA_URL.lstrip('/')}fire_alerts/{filename}",
            "persistence_state": "queued",
            "persistence_error": "",
        }
        with self._lock:
            self._events.appendleft(event)
        if self._webhook.enabled:
            try:
                if not self._webhook.submit(event, detections, event_dir / filename):
                    self._update_event_webhook(event["id"], "queue_full", "Hàng đợi n8n đã đầy.")
            except Exception:
                self._update_event_webhook(event["id"], "failed", WEBHOOK_ERROR)
        try:
            if not self._persistence.submit(event["id"], detections, event["image_url"]):
                self._update_event_persistence(event["id"], "queue_full", QUEUE_FULL_ERROR)
        except Exception:
            logger.exception("Could not enqueue webcam alert persistence")
            self._update_event_persistence(event["id"], "failed", PERSISTENCE_ERROR)
        return True


detector = WebcamFireDetector()
