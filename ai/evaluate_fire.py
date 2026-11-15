"""Evaluate fixed operating thresholds on an independent YOLO-format image list.

Uses IoU>=0.5, counts every prediction, and reports recall on fire boxes occupying
at most 1% of the image. This is not a claim of real-world fire-safety performance.
No webcam, database, uploads or image modification are involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path


def label_path(image: Path) -> Path:
    return image.parent.parent / "labels" / (image.stem + ".txt")


def labels(image: Path):
    result = []
    annotation_path = label_path(image)
    for line_number, line in enumerate(annotation_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cls, cx, cy, width, height = map(float, line.split())
        except ValueError:
            raise ValueError(f"{annotation_path}:{line_number}: expected five numeric YOLO fields") from None
        if (not all(math.isfinite(value) for value in (cls, cx, cy, width, height))
                or cls not in (0, 1) or not cls.is_integer()
                or not 0 <= cx <= 1 or not 0 <= cy <= 1
                or not 0 < width <= 1 or not 0 < height <= 1):
            raise ValueError(
                f"{annotation_path}:{line_number}: class must be 0 or 1, "
                "coordinates finite/normalized, and width/height positive"
            )
        result.append({"class": int(cls), "xyxy": [cx - width / 2, cy - height / 2,
                                                    cx + width / 2, cy + height / 2],
                       "small": width * height <= 0.01})
    return result


def validate_output_path(output: Path, *inputs: Path) -> None:
    if output.resolve() in {path.resolve() for path in inputs}:
        raise ValueError("Evaluation output must not overwrite a model or image-list input")


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = max(0, a[2] - a[0]) * max(0, a[3] - a[1]) + max(0, b[2] - b[0]) * max(0, b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


def operating_metrics(records, fire_threshold, smoke_threshold):
    counts = {name: {"tp": 0, "fp": 0, "gt": 0, "small_tp": 0, "small_gt": 0}
              for name in ("smoke", "fire")}
    negative_images = negative_alerts = 0
    for record in records:
        ground_truth = record["labels"]
        matched = set()
        predictions = sorted((p for p in record["predictions"] if p["confidence"] >= (
            fire_threshold if p["class"] == 1 else smoke_threshold)), key=lambda p: -p["confidence"])
        if not ground_truth:
            negative_images += 1
            negative_alerts += bool(predictions)
        for box in ground_truth:
            count = counts["fire" if box["class"] == 1 else "smoke"]
            count["gt"] += 1
            count["small_gt"] += box["small"]
        for prediction in predictions:
            count = counts["fire" if prediction["class"] == 1 else "smoke"]
            candidates = [(iou(prediction["xyxy"], box["xyxy"]), index)
                          for index, box in enumerate(ground_truth)
                          if box["class"] == prediction["class"] and index not in matched]
            overlap, index = max(candidates, default=(0, -1))
            if overlap >= 0.5:
                matched.add(index)
                count["tp"] += 1
                count["small_tp"] += ground_truth[index]["small"]
            else:
                count["fp"] += 1
    for count in counts.values():
        count["precision"] = round(count["tp"] / max(1, count["tp"] + count["fp"]), 4)
        count["recall"] = round(count["tp"] / max(1, count["gt"]), 4)
        count["small_recall"] = round(count["small_tp"] / max(1, count["small_gt"]), 4)
    return {"fire_threshold": fire_threshold, "smoke_threshold": smoke_threshold,
            "classes": counts, "negative_images": negative_images,
            "negative_false_alert_images": negative_alerts,
            "negative_false_alert_rate": round(negative_alerts / max(1, negative_images), 4)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--imgsz", type=int, default=768)
    parser.add_argument("--device", default="0")
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--max-det", type=int, default=300)
    parser.add_argument("--fire-thresholds", default="0.15,0.20,0.25,0.30,0.35")
    parser.add_argument("--smoke-threshold", type=float, default=0.55)
    args = parser.parse_args()
    validate_output_path(args.output, args.model, args.images)
    paths = [Path(line.strip()).resolve() for line in args.images.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("Evaluation image list is empty or contains duplicates")
    ground_truth = {str(path): labels(path) for path in paths}
    # Pure metric/annotation checks do not import a GPU framework or load weights.
    import numpy as np
    from ultralytics import YOLO

    model = YOLO(str(args.model))
    if model.names != {0: "smoke", 1: "fire"}:
        raise ValueError(f"Unexpected model classes: {model.names}")
    started = time.perf_counter()
    records, inference_ms = [], []
    for index, result in enumerate(model.predict(source=str(args.images), imgsz=args.imgsz, device=args.device,
                                                  conf=0.05, iou=0.7, max_det=args.max_det,
                                                  batch=args.batch, stream=True, verbose=False)):
        predictions = []
        for coords, confidence, class_id in zip(result.boxes.xyxyn.cpu().numpy(),
                                                result.boxes.conf.cpu().numpy(), result.boxes.cls.cpu().numpy(),
                                                strict=True):
            predictions.append({"class": int(class_id), "confidence": float(confidence), "xyxy": coords.tolist()})
        path = str(Path(result.path).resolve())
        records.append({"path": path, "labels": ground_truth[path], "predictions": predictions})
        inference_ms.append(result.speed["inference"])
        if (index + 1) % 100 == 0:
            print(f"Evaluated {index + 1}/{len(paths)} images", flush=True)
    if len(records) != len(paths) or {r["path"] for r in records} != set(ground_truth):
        raise RuntimeError("Model did not evaluate the exact requested list")
    report = {
        "model": str(args.model.resolve()),
        "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "images_sha256": hashlib.sha256(args.images.read_bytes()).hexdigest(),
        "images": len(paths), "imgsz": args.imgsz, "iou": 0.5, "small_area_ratio": 0.01,
        "prediction_confidence_floor": 0.05, "prediction_nms_iou": 0.7, "prediction_max_det": args.max_det,
        "seconds": round(time.perf_counter() - started, 2),
        "mean_inference_ms": round(float(np.mean(inference_ms)), 2),
        "operating_points": [operating_metrics(records, float(threshold), args.smoke_threshold)
                             for threshold in args.fire_thresholds.split(",")],
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
