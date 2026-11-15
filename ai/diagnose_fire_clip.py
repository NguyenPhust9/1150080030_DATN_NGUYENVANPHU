"""Compare local detector outputs on extracted screen-recording frames.

This is a diagnostic replay, not a training set or independent accuracy test.
It deliberately does not count repeated recorded images as temporal confirmations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[512, 768, 1024])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mask-banner", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() in {args.model.resolve(), args.frames.resolve()}:
        parser.error("Choose a new report path; inputs and earlier reports are preserved")
    if any(size < 320 or size > 1536 or size % 32 for size in args.sizes):
        parser.error("Inference sizes must be multiples of 32 between 320 and 1536")
    manifest = json.loads((args.frames / "manifest.json").read_text(encoding="utf-8"))

    import cv2
    import numpy as np
    from ultralytics import YOLO

    frames, frame_meta = [], []
    previous = None
    for sample in manifest["samples"]:
        path = (args.frames / sample["file"]).resolve()
        if not path.is_relative_to(args.frames.resolve()):
            raise ValueError("Frame path escapes the chosen frame directory")
        frame = cv2.imread(str(path))
        if frame is None:
            raise ValueError(f"Unreadable frame: {path.name}")
        if args.mask_banner:
            x, y, w, h = args.mask_banner
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > frame.shape[1] or y + h > frame.shape[0]:
                raise ValueError("Banner mask must be within the frame")
            frame[y:y + h, x:x + w] = (24, 24, 24)
        difference = None if previous is None else float(np.abs(
            frame.astype(np.int16) - previous.astype(np.int16)).mean())
        frame_meta.append({**sample, "mean_pixel_difference_from_previous": difference,
                           "near_duplicate_of_previous": difference is not None and difference < 0.5})
        frames.append(frame)
        previous = frame
    model = YOLO(str(args.model))
    if model.names != {0: "smoke", 1: "fire"}:
        raise ValueError("Expected a smoke=0, fire=1 checkpoint")
    configurations = []
    for size in args.sizes:
        records = []
        # A single frame per call follows live inference padding (not batch padding).
        for meta, frame in zip(frame_meta, frames, strict=True):
            result = model.predict(frame, imgsz=size, conf=0.05, iou=0.7, max_det=300,
                                   device=0, verbose=False)[0]
            predictions = [{"label": result.names[int(box.cls.item())],
                            "confidence": round(float(box.conf.item()), 5),
                            "xyxy": [round(v, 2) for v in box.xyxy[0].tolist()]}
                           for box in result.boxes]
            records.append({**meta, "predictions": predictions,
                            "maximum_fire_confidence": max(
                                (p["confidence"] for p in predictions if p["label"] == "fire"), default=0),
                            "inference_ms": result.speed["inference"]})
        summary = {
            "imgsz": size, "sampled_frames": len(records),
            "frames_with_fire_at_025": sum(r["maximum_fire_confidence"] >= .25 for r in records),
            "frames_with_fire_at_015": sum(r["maximum_fire_confidence"] >= .15 for r in records),
            "near_duplicate_frames": sum(r["near_duplicate_of_previous"] for r in records),
            "median_inference_ms": round(float(np.median([r["inference_ms"] for r in records])), 2),
        }
        configurations.append({**summary, "records": records})
        print(json.dumps(summary), flush=True)
    report = {
        "purpose": "diagnostic_replay_only_not_independent_accuracy_evaluation",
        "video_sha256": manifest["video_sha256"], "crop_xywh": manifest["crop_xywh"],
        "mask_banner_xywh": args.mask_banner,
        "model": str(args.model.resolve()), "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "warnings": ["Screen recording contains preexisting detector boxes and recompressed webcam images.",
                     "Recorded repeated images must not count as independent temporal confirmations.",
                     "Detection-frame counts are not accuracy/recall; there are no ground-truth boxes here.",
                     "This clip has not been used for training or selection of a production threshold."],
        "configurations": configurations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Saved diagnostic report: {args.output}")


if __name__ == "__main__":
    main()
