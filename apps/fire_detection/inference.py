"""Small, testable inference rules; importing this module never opens a camera."""

import math
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DetectorConfig:
    model_path: Path
    camera_index: int = 0
    image_size: int = 512
    fire_confidence: float = 0.25
    smoke_confidence: float = 0.55
    confirm_frames: int = 2
    confirmation_window: int = 5
    cooldown_seconds: int = 30
    stale_after_seconds: float = 10.0

    @classmethod
    def from_environment(cls, base_dir, environ=None):
        environ = os.environ if environ is None else environ

        def integer(name, default, minimum, maximum):
            try:
                value = int(environ.get(name, default))
            except (ValueError, TypeError):
                raise ValueError(f"{name} phải là số nguyên.") from None
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} phải nằm trong khoảng {minimum}–{maximum}.")
            return value

        def confidence(name, default):
            try:
                value = float(environ.get(name, default))
            except (ValueError, TypeError):
                raise ValueError(f"{name} phải là số trong khoảng 0.01–1.") from None
            if not math.isfinite(value) or not 0.01 <= value <= 1:
                raise ValueError(f"{name} phải nằm trong khoảng 0.01–1.")
            return value

        image_size = integer("FIRE_IMAGE_SIZE", 512, 320, 1536)
        if image_size % 32:
            raise ValueError("FIRE_IMAGE_SIZE phải là bội số của 32.")
        configured_path = Path(environ.get(
            "FIRE_MODEL_PATH", "runs/fire_detection/dfire_yolo11n_e30/weights/best.pt"
        ))
        return cls(
            model_path=(configured_path if configured_path.is_absolute()
                        else Path(base_dir) / configured_path),
            camera_index=integer("FIRE_CAMERA_INDEX", 0, 0, 99),
            image_size=image_size,
            fire_confidence=confidence("FIRE_CONFIDENCE", 0.25),
            smoke_confidence=confidence("SMOKE_CONFIDENCE", 0.55),
            confirm_frames=integer("FIRE_CONFIRM_FRAMES", 2, 1, 5),
            cooldown_seconds=integer("FIRE_ALERT_COOLDOWN_SECONDS", 30, 1, 86400),
        )


def validate_model_classes(names):
    """Do not silently run a generic COCO model as a fire/smoke detector."""
    values = names.values() if isinstance(names, dict) else names
    labels = {str(name).strip().lower() for name in values}
    missing = {"fire", "smoke"} - labels
    if missing:
        raise ValueError(
            "Mô hình không phù hợp: thiếu lớp " + ", ".join(sorted(missing))
            + ". Hãy chọn mô hình đã huấn luyện nhận diện cả fire và smoke."
        )


def filter_detections(result, frame_shape, config):
    """Keep valid fire/smoke boxes, without discarding tiny fire or large smoke."""
    detections = []
    if result.boxes is None:
        return detections
    height, width = frame_shape[:2]
    for box in result.boxes:
        class_id = int(box.cls.item())
        label = str(result.names[class_id]).strip().lower()
        if label not in {"fire", "smoke"}:
            continue
        score = float(box.conf.item())
        minimum = config.fire_confidence if label == "fire" else config.smoke_confidence
        if not math.isfinite(score) or not minimum <= score <= 1:
            continue
        coordinates = box.xyxy[0].tolist()
        if len(coordinates) != 4 or not all(math.isfinite(value) for value in coordinates):
            continue
        x1, y1, x2, y2 = [int(value) for value in coordinates]
        x1, x2 = max(0, min(x1, width)), max(0, min(x2, width))
        y1, y2 = max(0, min(y1, height)), max(0, min(y2, height))
        if x2 <= x1 or y2 <= y1:
            continue
        detections.append({"label": label, "confidence": round(score, 3),
                           "xyxy": (x1, y1, x2, y2)})
    return detections


class TemporalConfirmation:
    """Confirm each class across recent frames; retain its actual positive evidence."""

    def __init__(self, required=2, window_size=5):
        if not 1 <= required <= window_size:
            raise ValueError("Confirmation count must fit the frame window.")
        self.required = required
        self.window = deque(maxlen=window_size)

    def clear(self):
        self.window.clear()

    def update(self, detections):
        self.window.append(tuple(dict(item) for item in detections))
        counts = {
            label: sum(any(item["label"] == label for item in frame) for frame in self.window)
            for label in ("fire", "smoke")
        }
        confirmed = {label for label, count in counts.items() if count >= self.required}
        evidence = []
        for label in sorted(confirmed):
            for frame in reversed(self.window):
                matching = [item for item in frame if item["label"] == label]
                if matching:
                    evidence.extend(matching)
                    break
        state = "alert" if confirmed else (
            "detecting" if any(self.window) else "monitoring"
        )
        return state, evidence
