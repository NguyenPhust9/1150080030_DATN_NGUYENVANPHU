from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train YOLO on D-Fire.")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--name", default="dfire_yolo11n")
    parser.add_argument("--project", default="runs/fire_detection")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    model = YOLO(args.model)
    model.train(
        data=str(root / "ai" / "dfire.yaml"),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        fraction=args.fraction,
        cache=args.cache,
        project=str(root / args.project),
        name=args.name,
        pretrained=True,
        patience=15,
        seed=42,
        deterministic=True,
        plots=True,
        save=True,
    )


if __name__ == "__main__":
    main()
