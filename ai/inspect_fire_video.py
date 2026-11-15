"""Extract local diagnostic frames; never open a webcam or modify the input video."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--step", type=float, default=3.0)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--crop", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    args = parser.parse_args()
    if (not args.video.is_file() or not math.isfinite(args.step) or args.step <= 0
            or not math.isfinite(args.start) or args.start < 0
            or (args.end is not None and not math.isfinite(args.end))):
        parser.error("A local video file and a positive frame interval are required")
    if args.output.exists():
        parser.error("Choose a new output directory to preserve earlier diagnostic frames")

    import cv2
    import numpy as np

    capture = cv2.VideoCapture(str(args.video.resolve()))
    if not capture.isOpened():
        raise ValueError("Could not decode the input video")
    fps = capture.get(cv2.CAP_PROP_FPS)
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or frames <= 0:
        capture.release()
        raise ValueError("Invalid video timing metadata")
    first = round(args.start * fps)
    last = min(frames, round(args.end * fps)) if args.end is not None else frames
    if first >= last:
        capture.release()
        raise ValueError("Requested time range is empty")
    if args.crop:
        x, y, w, h = args.crop
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            capture.release()
            raise ValueError("Crop must be inside the video frame")
    args.output.mkdir(parents=True)
    rows, previews = [], []
    try:
        for index in range(first, last, max(1, round(args.step * fps))):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"Could not decode frame {index}")
            if args.crop:
                frame = frame[y:y + h, x:x + w]
            name = f"frame_{index:06d}.jpg"
            if not cv2.imwrite(str(args.output / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 96]):
                raise OSError(f"Could not save {name}")
            rows.append({"frame": index, "seconds": round(index / fps, 3), "file": name})
            scale = 440 / frame.shape[1]
            preview = cv2.resize(frame, (440, round(frame.shape[0] * scale)))
            preview = cv2.copyMakeBorder(preview, 28, 0, 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30))
            cv2.putText(preview, f"{index / fps:.2f}s / frame {index}", (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
            previews.append(preview)
    finally:
        capture.release()
    for offset in range(0, len(previews), 12):
        page = previews[offset:offset + 12]
        while len(page) % 3:
            page.append(np.zeros_like(page[0]))
        sheet = np.vstack([np.hstack(page[i:i + 3]) for i in range(0, len(page), 3)])
        cv2.imwrite(str(args.output / f"contact_{offset // 12:02d}.jpg"), sheet)
    manifest = {"video": str(args.video.resolve()), "video_sha256": hashlib.sha256(args.video.read_bytes()).hexdigest(),
                "fps": fps, "frames": frames, "duration_seconds": round(frames / fps, 3),
                "width": width, "height": height, "crop_xywh": args.crop, "samples": rows,
                "start_seconds": first / fps, "end_seconds": last / fps,
                "purpose": "local diagnosis only; these frames are not independent training/test sessions"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "samples"}, indent=2))
    print(f"Extracted {len(rows)} frames into {args.output}")


if __name__ == "__main__":
    main()
