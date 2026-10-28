from __future__ import annotations

import argparse
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare D-Fire fold 1 for Ultralytics YOLO.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "datasets" / "D-Fire",
    )
    return parser.parse_args()


def read_names(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_pair(dataset: Path, split: str, name: str) -> tuple[Path, Path]:
    image = dataset / split / "images" / name
    label = dataset / split / "labels" / f"{Path(name).stem}.txt"
    if not image.is_file():
        raise FileNotFoundError(f"Missing image: {image}")
    if not label.is_file():
        raise FileNotFoundError(f"Missing label: {label}")
    return image, label


def write_list(path: Path, images: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(image.as_posix() for image in images) + "\n", encoding="utf-8")


def main() -> None:
    dataset = parse_args().dataset.resolve()
    fold_dir = dataset / "Data splitting" / "5-fold cross validation"
    output_dir = dataset / "yolo_splits"

    train_names = read_names(fold_dir / "dfire_train1.txt")
    val_names = read_names(fold_dir / "dfire_valid1.txt")
    test_names = sorted(
        path.name for path in (dataset / "test" / "images").iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS
    )

    train_images = [verify_pair(dataset, "train", name)[0] for name in train_names]
    val_images = [verify_pair(dataset, "train", name)[0] for name in val_names]
    test_images = [verify_pair(dataset, "test", name)[0] for name in test_names]

    if set(train_names) & set(val_names):
        raise ValueError("Fold 1 train and validation lists overlap")

    write_list(output_dir / "train.txt", train_images)
    write_list(output_dir / "val.txt", val_images)
    write_list(output_dir / "test.txt", test_images)

    print(f"Prepared D-Fire: train={len(train_images)}, val={len(val_images)}, test={len(test_images)}")
    print(f"Lists written to: {output_dir}")


if __name__ == "__main__":
    main()
