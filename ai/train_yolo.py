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
    parser.add_argument("--data", type=Path, help="Optional prepared dataset YAML (train/val remain separate).")
    parser.add_argument("--optimizer", default="auto")
    parser.add_argument("--lr0", type=float, help="Explicit initial learning rate for fine-tuning.")
    parser.add_argument("--freeze", type=int, default=0, help="Freeze first N layers for a memory-efficient fine-tune.")
    parser.add_argument("--mosaic", type=float, default=1.0)
    parser.add_argument("--scale", type=float, default=0.5)
    parser.add_argument("--close-mosaic", type=int, default=10)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--save-period", type=int, default=-1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    model = YOLO(args.model)
    tuning = {"lr0": args.lr0} if args.lr0 is not None else {}
    model.train(
        data=str(args.data.resolve() if args.data else root / "ai" / "dfire.yaml"),
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
        patience=args.patience,
        optimizer=args.optimizer,
        freeze=args.freeze,
        mosaic=args.mosaic,
        scale=args.scale,
        close_mosaic=min(args.close_mosaic, args.epochs),
        save_period=args.save_period,
        seed=42,
        deterministic=True,
        plots=True,
        save=True,
        **tuning,
    )


if __name__ == "__main__":
    main()
