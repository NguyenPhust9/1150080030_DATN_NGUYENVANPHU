"""Export the trained checkpoint for request-by-request Vercel inference.

Run locally with the training dependencies plus onnx installed. Never runs on import.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def main():
    from ultralytics import YOLO
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=Path("runs/fire_detection/dfire_yolo11n_e30/weights/best.pt"))
    parser.add_argument("--output", type=Path, default=Path("models/fire_detection.onnx"))
    args = parser.parse_args()
    model = YOLO(str(args.checkpoint))
    if set(model.names.values()) != {"fire", "smoke"}:
        raise ValueError("Expected the trained two-class fire/smoke checkpoint")
    exported = Path(model.export(format="onnx", imgsz=512, opset=17, dynamic=False, simplify=False, nms=False, device="cpu"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if exported.resolve() != args.output.resolve():
        shutil.copy2(exported, args.output)
    metadata = {
        "source": args.checkpoint.as_posix(),
        "source_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        "onnx_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "image_size": 512, "names": model.names, "opset": 17, "dynamic": False, "nms": False,
    }
    args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {args.output}")


if __name__ == "__main__":
    main()
