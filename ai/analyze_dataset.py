from collections import Counter
from pathlib import Path


def analyze_split(root: Path, split: str) -> dict:
    list_path = root / "yolo_splits" / f"{split}.txt"
    image_paths = [Path(line.strip()) for line in list_path.read_text().splitlines() if line.strip()]
    classes = Counter()
    empty = missing = malformed = small = 0
    areas = []
    for image_path in image_paths:
        label_path = image_path.parent.parent / "labels" / f"{image_path.stem}.txt"
        if not label_path.exists():
            missing += 1
            continue
        lines = [line.strip() for line in label_path.read_text(errors="ignore").splitlines() if line.strip()]
        if not lines:
            empty += 1
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 5:
                malformed += 1
                continue
            try:
                class_id = int(float(parts[0]))
                area = float(parts[3]) * float(parts[4])
            except ValueError:
                malformed += 1
                continue
            classes[class_id] += 1
            areas.append(area)
            small += area < 0.01
    boxes = sum(classes.values())
    return {
        "images": len(image_paths),
        "empty": empty,
        "missing_labels": missing,
        "malformed": malformed,
        "boxes": boxes,
        "classes": dict(classes),
        "small_boxes_under_1pct": small,
        "small_pct": round(100 * small / boxes, 1) if boxes else 0,
        "median_box_area_pct": round(100 * sorted(areas)[len(areas) // 2], 2) if areas else 0,
    }


if __name__ == "__main__":
    dataset_root = Path(__file__).resolve().parents[1] / "datasets" / "D-Fire"
    for split_name in ("train", "val", "test"):
        print(split_name, analyze_split(dataset_root, split_name))
