"""CPU inference for one browser frame; no camera, cv2, torch or background loop."""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from django.conf import settings
from PIL import Image

from .inference import DetectorConfig, validate_model_classes


@lru_cache(maxsize=1)
def get_model():
    import onnxruntime as ort
    path = Path(settings.BASE_DIR) / "models/fire_detection.onnx"
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    names = {int(key): value for key, value in metadata["names"].items()}
    validate_model_classes(names)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
    size = int(session.get_inputs()[0].shape[2])
    if size != metadata["image_size"] or session.get_inputs()[0].shape != [1, 3, size, size]:
        raise ValueError("Unexpected exported model shape")
    return session, size, names


def decode_predictions(output, names, size, width, height, scale, left, top, config):
    rows = np.asarray(output)[0].T
    if rows.ndim != 2 or rows.shape[1] != 4 + len(names):
        raise ValueError("Unexpected YOLO output shape")
    ids = rows[:, 4:].argmax(axis=1)
    scores = rows[np.arange(len(rows)), 4 + ids]
    minimums = np.array([config.fire_confidence if names[int(idx)] == "fire" else config.smoke_confidence for idx in ids])
    valid = np.isfinite(rows).all(axis=1) & (scores >= minimums) & (scores <= 1)
    candidates = []
    for index in np.flatnonzero(valid)[np.argsort(-scores[valid])[:3000]]:
        x, y, w, h = rows[index, :4]
        x1 = max(0, min(width, int((x - w / 2 - left) / scale)))
        y1 = max(0, min(height, int((y - h / 2 - top) / scale)))
        x2 = max(0, min(width, int((x + w / 2 - left) / scale)))
        y2 = max(0, min(height, int((y + h / 2 - top) / scale)))
        if x2 > x1 and y2 > y1:
            candidates.append({"label": names[int(ids[index])], "confidence": round(float(scores[index]), 3), "xyxy": [x1, y1, x2, y2]})
    kept = []
    for candidate in candidates:
        x1, y1, x2, y2 = candidate["xyxy"]
        overlap = False
        for existing in kept:
            if existing["label"] != candidate["label"]:
                continue
            a, b, c, d = existing["xyxy"]
            intersection = max(0, min(x2, c) - max(x1, a)) * max(0, min(y2, d) - max(y1, b))
            union = (x2 - x1) * (y2 - y1) + (c - a) * (d - b) - intersection
            if union > 0 and intersection / union > 0.7:
                overlap = True
                break
        if not overlap:
            kept.append(candidate)
            if len(kept) == 300:
                break
    return kept


def predict_image(image):
    session, size, names = get_model()
    width, height = image.size
    scale = min(size / width, size / height)
    resized = image.convert("RGB").resize((round(width * scale), round(height * scale)), Image.Resampling.BILINEAR)
    left, top = (size - resized.width) // 2, (size - resized.height) // 2
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    canvas.paste(resized, (left, top))
    tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
    output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
    config = DetectorConfig.from_environment(settings.BASE_DIR)
    return decode_predictions(output, names, size, width, height, scale, left, top, config)
