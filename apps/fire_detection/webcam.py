import asyncio
import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from django.conf import settings


class WebcamFireDetector:
    def __init__(self):
        self._lock = threading.RLock()
        self._thread = None
        self._stop_event = threading.Event()
        self._frame = None
        self._running = False
        self._loading = False
        self._error = ""
        self._state = "stopped"
        self._detections = []
        self._events = deque(maxlen=10)
        self._last_alert_at = 0.0
        self._confirmed_frames = 0
        self._danger_window = deque(maxlen=5)
        self._fps = 0.0

    @property
    def model_path(self):
        configured = os.getenv(
            "FIRE_MODEL_PATH",
            "runs/fire_detection/dfire_yolo11n_e30/weights/best.pt",
        )
        path = Path(configured)
        return path if path.is_absolute() else settings.BASE_DIR / path

    def start(self):
        with self._lock:
            if self._running or self._loading:
                return True, "Camera đang hoạt động."
            if not self.model_path.is_file():
                self._error = f"Không tìm thấy mô hình: {self.model_path}"
                self._state = "error"
                return False, self._error
            self._stop_event.clear()
            self._loading = True
            self._error = ""
            self._state = "starting"
            self._thread = threading.Thread(target=self._run, name="fire-webcam", daemon=True)
            self._thread.start()
        return True, "Đang khởi động camera và mô hình AI."

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=3)
        with self._lock:
            self._running = False
            self._loading = False
            self._state = "stopped"
            self._detections = []
            self._confirmed_frames = 0
            self._danger_window.clear()

    def snapshot(self):
        with self._lock:
            return {
                "running": self._running,
                "loading": self._loading,
                "state": self._state,
                "error": self._error,
                "fps": round(self._fps, 1),
                "detections": list(self._detections),
                "events": list(self._events),
                "model_name": self.model_path.name,
                "camera_index": int(os.getenv("FIRE_CAMERA_INDEX", "0")),
            }

    async def mjpeg_frames(self):
        while True:
            with self._lock:
                frame = self._frame
                active = self._running or self._loading
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            if not active and self._stop_event.is_set():
                break
            await asyncio.sleep(0.05)

    def _run(self):
        capture = None
        try:
            import cv2
            from ultralytics import YOLO

            model = YOLO(str(self.model_path))
            camera_index = int(os.getenv("FIRE_CAMERA_INDEX", "0"))
            capture = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not capture.isOpened():
                capture.release()
                capture = cv2.VideoCapture(camera_index)
            if not capture.isOpened():
                raise RuntimeError(
                    f"Không mở được webcam số {camera_index}. Hãy đóng ứng dụng khác đang dùng camera."
                )
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            # Webcam flames are often small and overexposed, so use a lower
            # inference threshold and rely on temporal confirmation to limit
            # false alarms.
            fire_confidence = float(os.getenv("FIRE_CONFIDENCE", "0.25"))
            smoke_confidence = float(os.getenv("SMOKE_CONFIDENCE", "0.55"))
            inference_confidence = min(fire_confidence, smoke_confidence)
            confirm_frames = max(1, int(os.getenv("FIRE_CONFIRM_FRAMES", "2")))
            cooldown = max(1, int(os.getenv("FIRE_ALERT_COOLDOWN_SECONDS", "30")))
            with self._lock:
                self._running = True
                self._loading = False
                self._state = "safe"

            last_tick = time.perf_counter()
            while not self._stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError("Mất kết nối với webcam.")

                result = model.predict(frame, imgsz=512, conf=inference_confidence, verbose=False)[0]
                detections = []
                has_danger = False
                if result.boxes is not None:
                    for box in result.boxes:
                        class_id = int(box.cls.item())
                        score = float(box.conf.item())
                        label = str(result.names[class_id]).lower()
                        if label not in {"fire", "smoke"}:
                            continue
                        x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
                        frame_area = max(frame.shape[0] * frame.shape[1], 1)
                        box_area_ratio = max(0, x2 - x1) * max(0, y2 - y1) / frame_area
                        minimum_score = fire_confidence if label == "fire" else smoke_confidence
                        # Motion blur close to the lens often becomes one huge
                        # false smoke box. Real early-smoke alerts should be
                        # localized and supported by a stronger score.
                        if score < minimum_score or (label == "smoke" and box_area_ratio > 0.45):
                            continue
                        has_danger = True
                        detections.append(
                            {
                                "label": label,
                                "confidence": round(score, 3),
                                "xyxy": (x1, y1, x2, y2),
                            }
                        )

                self._danger_window.append(has_danger)
                self._confirmed_frames = sum(self._danger_window)
                alert = self._confirmed_frames >= confirm_frames
                is_verifying = has_danger or any(self._danger_window)
                state = "alert" if alert else ("detecting" if is_verifying else "safe")
                annotated = frame.copy()
                for detection in detections:
                    x1, y1, x2, y2 = detection["xyxy"]
                    label = detection["label"]
                    box_color = (0, 70, 255) if label == "fire" else (255, 170, 0)
                    caption = f"{label} {detection['confidence']:.2f}"
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)
                    cv2.putText(
                        annotated,
                        caption,
                        (x1, max(22, y1 - 7)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        box_color,
                        2,
                    )
                color = (0, 0, 255) if alert else (0, 180, 0)
                detected_labels = {item["label"] for item in detections}
                if alert:
                    text = "CANH BAO LUA" if "fire" in detected_labels else "CANH BAO KHOI"
                else:
                    text = "DANG XAC MINH" if is_verifying else "AN TOAN"
                cv2.rectangle(annotated, (10, 10), (350, 62), (15, 20, 32), -1)
                cv2.putText(annotated, text, (24, 47), cv2.FONT_HERSHEY_SIMPLEX, 0.82, color, 2)

                if alert and time.time() - self._last_alert_at >= cooldown:
                    self._last_alert_at = time.time()
                    self._save_event(annotated, detections, cv2)

                encoded, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
                now = time.perf_counter()
                elapsed = max(now - last_tick, 0.001)
                last_tick = now
                with self._lock:
                    if encoded:
                        self._frame = buffer.tobytes()
                    self._state = state
                    self._detections = detections
                    self._fps = 1.0 / elapsed
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
                self._state = "error"
        finally:
            if capture is not None:
                capture.release()
            with self._lock:
                self._running = False
                self._loading = False

    def _save_event(self, frame, detections, cv2):
        event_dir = settings.MEDIA_ROOT / "fire_alerts"
        event_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"fire_alert_{stamp}.jpg"
        cv2.imwrite(str(event_dir / filename), frame)
        labels = sorted({item["label"] for item in detections})
        event = {
            "time": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
            "labels": labels,
            "image_url": f"/{settings.MEDIA_URL.lstrip('/')}fire_alerts/{filename}",
        }
        with self._lock:
            self._events.appendleft(event)


detector = WebcamFireDetector()
