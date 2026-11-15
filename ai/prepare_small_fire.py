"""Build reproducible small-fire-focused manifests without moving source data.

The original train/validation/test membership is never changed. This is a
focused evaluation subset, not a claim of representative deployment accuracy.
Run ``python ai/prepare_small_fire.py``; only datasets/D-Fire/small_fire_v1 is
written. Labels remain smoke=0 and fire=1, matching the original D-Fire data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path

GROUPS = ("small_fire", "other_positive", "negative")


def label_path(image: Path) -> Path:
    if image.parent.name != "images":
        raise ValueError(f"Expected an images directory: {image}")
    return image.parent.parent / "labels" / f"{image.stem}.txt"


def inspect_image(image: Path, max_fire_area: float) -> dict:
    if not image.is_file():
        raise FileNotFoundError(image)
    label = label_path(image)
    # A missing annotation is an error, never silently a negative example.
    rows = label.read_text(encoding="utf-8-sig").splitlines()
    counts = Counter()
    fire_areas = []
    for line_number, row in enumerate(rows, 1):
        if not row.strip():
            continue
        parts = row.split()
        if len(parts) != 5:
            raise ValueError(f"Malformed YOLO row: {label}:{line_number}")
        class_id = int(parts[0])
        coordinates = [float(value) for value in parts[1:]]
        if class_id not in (0, 1) or any(
            not math.isfinite(value) or not 0 <= value <= 1
            for value in coordinates
        ) or min(coordinates[2:]) <= 0:
            raise ValueError(f"Invalid YOLO values: {label}:{line_number}")
        counts[class_id] += 1
        if class_id == 1:
            fire_areas.append(coordinates[2] * coordinates[3])
    small_count = sum(area <= max_fire_area for area in fire_areas)
    group = "small_fire" if small_count else "other_positive" if counts else "negative"
    return {
        "path": image.as_posix(),
        "group": group,
        "smoke_objects": counts[0],
        "fire_objects": counts[1],
        "small_fire_objects": small_count,
        "smallest_fire_area": min(fire_areas) if fire_areas else None,
    }


def summarize(records: list[dict]) -> dict:
    return {
        "images": len(records),
        "groups": {group: sum(row["group"] == group for row in records) for group in GROUPS},
        "smoke_only_images": sum(row["smoke_objects"] > 0 and row["fire_objects"] == 0 for row in records),
        "smoke_objects": sum(row["smoke_objects"] for row in records),
        "fire_objects": sum(row["fire_objects"] for row in records),
        "small_fire_objects": sum(row["small_fire_objects"] for row in records),
    }


def sample_split(records: list[dict], target: int, seed: int) -> list[dict]:
    """Upweight small fires while preserving both smoke and empty controls."""
    rng = random.Random(seed)
    pools = {group: sorted((row for row in records if row["group"] == group), key=lambda row: row["path"]) for group in GROUPS}
    target = min(target, len(records))
    desired = {"small_fire": target // 2, "negative": target // 4}
    desired["other_positive"] = target - sum(desired.values())
    quota = {group: min(desired[group], len(pools[group])) for group in GROUPS}
    # When small fires are scarce, use other positives first, retaining negative
    # controls. Never borrow examples from validation or test to fill training.
    missing = target - sum(quota.values())
    for group in ("other_positive", "negative", "small_fire"):
        extra = min(missing, len(pools[group]) - quota[group])
        quota[group] += extra
        missing -= extra
    selected = []
    for group in GROUPS:
        pool = pools[group]
        if group == "other_positive":
            smoke_only = [row for row in pool if row["fire_objects"] == 0]
            other_fire = [row for row in pool if row["fire_objects"] > 0]
            smoke_count = min(len(smoke_only), quota[group] // 2)
            fire_count = min(len(other_fire), quota[group] - smoke_count)
            smoke_count = min(len(smoke_only), quota[group] - fire_count)
            selected.extend(rng.sample(smoke_only, smoke_count))
            selected.extend(rng.sample(other_fire, fire_count))
        else:
            selected.extend(rng.sample(pool, quota[group]))
    rng.shuffle(selected)
    if len(selected) != target:
        raise ValueError("Sampling did not meet target")
    return selected


def normalized_paths(records: list[dict]) -> set[str]:
    # Windows path identity is case-insensitive; use casefold on all platforms
    # so manifests remain conservative if copied between operating systems.
    return {row["path"].casefold() for row in records}


def assert_disjoint(splits: dict[str, list[dict]]) -> None:
    known: set[str] = set()
    for name, records in splits.items():
        paths = normalized_paths(records)
        if len(paths) != len(records):
            raise ValueError(f"Duplicate image path within {name}")
        if paths & known:
            raise ValueError(f"Image path leaks across splits: {name}")
        known |= paths


def build(dataset: Path, output: Path, sizes: dict[str, int], seed: int, max_fire_area: float) -> dict:
    dataset = dataset.resolve()
    output = output.resolve()
    if dataset not in output.parents or output == dataset / "yolo_splits":
        raise ValueError("Output must be a separate subdirectory of the dataset")
    originals = {}
    invalid_labels = {}
    source_hashes = {}
    for name in ("train", "val", "test"):
        source = dataset / "yolo_splits" / f"{name}.txt"
        source_hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        paths = []
        for line in source.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            image = Path(line.strip())
            if not image.is_absolute():
                image = dataset / image
            image = image.resolve()
            if dataset not in image.parents:
                raise ValueError(f"Image is outside the dataset: {image}")
            paths.append(image)
        originals[name] = []
        invalid_labels[name] = []
        for path in paths:
            try:
                originals[name].append(inspect_image(path, max_fire_area))
            except ValueError as exc:
                # Exclude the whole image instead of silently dropping a bad
                # object or modifying annotations owned by the source dataset.
                invalid_labels[name].append({"path": path.as_posix(), "reason": str(exc)})
    assert_disjoint(originals)
    selected = {name: sample_split(originals[name], sizes[name], seed + index) for index, name in enumerate(originals)}
    assert_disjoint(selected)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "seed": seed,
        "class_names": {"0": "smoke", "1": "fire"},
        "small_fire_max_normalized_box_area": max_fire_area,
        "dataset": dataset.as_posix(),
        "source_list_sha256": source_hashes,
        "source_audit": {name: summarize(records) for name, records in originals.items()},
        "excluded_invalid_labels": invalid_labels,
        "selected": {},
        "notes": [
            "Every split uses only its original split; original files are untouched.",
            "Images containing a fire box with normalized width*height <= threshold count as small_fire.",
            "Smoke-only and empty annotated images are included as controls.",
            "Hashes cover list contents, not image pixels; path isolation is checked, near-duplicate imagery is not.",
            "Focused validation/test metrics are not representative of all deployment scenes.",
        ],
    }
    for name, records in selected.items():
        listing = "\n".join(row["path"] for row in records) + "\n"
        # Bytes are explicit so manifest hashes stay stable across platforms.
        (output / f"{name}.txt").write_bytes(listing.encode("utf-8"))
        manifest["selected"][name] = {
            **summarize(records),
            "list_sha256": hashlib.sha256(listing.encode("utf-8")).hexdigest(),
            "small_fire_examples": [row["path"] for row in records if row["group"] == "small_fire"][:8],
        }
    # JSON-quoted paths are legal YAML and handle spaces/backslashes safely.
    yaml = "\n".join([
        f"path: {json.dumps(dataset.as_posix())}",
        *[f"{name}: {json.dumps((output / f'{name}.txt').as_posix())}" for name in selected],
        "names:", "  0: smoke", "  1: fire", "",
    ])
    (output / "dataset.yaml").write_text(yaml, encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parents[1] / "datasets" / "D-Fire")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--train-size", type=int, default=2400)
    parser.add_argument("--val-size", type=int, default=400)
    parser.add_argument("--test-size", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-fire-area", type=float, default=0.01)
    args = parser.parse_args()
    sizes = {"train": args.train_size, "val": args.val_size, "test": args.test_size}
    if min(sizes.values()) <= 0 or not 0 < args.max_fire_area <= 1:
        parser.error("Split sizes must be positive and max-fire-area must be in (0, 1]")
    output = args.output or args.dataset / "small_fire_v1"
    manifest = build(args.dataset, output, sizes, args.seed, args.max_fire_area)
    print(json.dumps({"source_audit": manifest["source_audit"], "excluded_invalid_label_counts": {name: len(rows) for name, rows in manifest["excluded_invalid_labels"].items()}, "selected": manifest["selected"], "yaml": (output.resolve() / "dataset.yaml").as_posix()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
