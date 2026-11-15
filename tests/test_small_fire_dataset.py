from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ai.prepare_small_fire import assert_disjoint, build, inspect_image, sample_split, summarize


class SmallFireDatasetTests(unittest.TestCase):
    def record(self, index, group, smoke=0, fire=0):
        return {
            "path": f"/images/{index}.jpg",
            "group": group,
            "smoke_objects": smoke,
            "fire_objects": fire,
            "small_fire_objects": int(group == "small_fire"),
        }

    def test_sampling_is_deterministic_balanced_and_retains_smoke(self):
        records = [self.record(f"s{i}", "small_fire", fire=1) for i in range(20)]
        records += [self.record(f"f{i}", "other_positive", fire=1) for i in range(10)]
        records += [self.record(f"m{i}", "other_positive", smoke=1) for i in range(10)]
        records += [self.record(f"n{i}", "negative") for i in range(10)]
        selected = sample_split(records, 40, 42)
        self.assertEqual(selected, sample_split(list(reversed(records)), 40, 42))
        self.assertEqual(summarize(selected)["groups"], {"small_fire": 20, "other_positive": 10, "negative": 10})
        self.assertEqual(summarize(selected)["smoke_only_images"], 5)

    def test_insufficient_small_fire_backfills_with_other_positives(self):
        records = [self.record("s", "small_fire", fire=1)]
        records += [self.record(f"f{i}", "other_positive", fire=1) for i in range(12)]
        records += [self.record(f"n{i}", "negative") for i in range(4)]
        self.assertEqual(summarize(sample_split(records, 16, 42))["groups"], {"small_fire": 1, "other_positive": 11, "negative": 4})

    def test_duplicates_and_cross_split_leakage_are_rejected(self):
        record = self.record("one", "negative")
        for splits in ({"train": [record, record]}, {"train": [record], "val": [record]}):
            with self.assertRaises(ValueError):
                assert_disjoint(splits)

    def create_pair(self, root, name, label):
        image = root / "images" / f"{name}.jpg"
        annotation = root / "labels" / f"{name}.txt"
        image.parent.mkdir(parents=True, exist_ok=True)
        annotation.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"fixture-image")
        annotation.write_text(label, encoding="utf-8")
        return image

    def test_small_fire_uses_box_area_and_empty_annotations_are_negative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            small = self.create_pair(root, "small", "1 0.5 0.5 0.05 0.08\n0 0.5 0.5 0.3 0.3\n")
            empty = self.create_pair(root, "empty", "")
            self.assertEqual(inspect_image(small, 0.01)["group"], "small_fire")
            self.assertEqual(inspect_image(empty, 0.01)["group"], "negative")

    def test_missing_annotation_is_not_silently_a_negative(self):
        with tempfile.TemporaryDirectory() as directory:
            image = self.create_pair(Path(directory), "missing", "")
            image.parent.parent.joinpath("labels", "missing.txt").unlink()
            with self.assertRaises(FileNotFoundError):
                inspect_image(image, 0.01)

    def test_build_preserves_sources_excludes_invalid_and_hashes_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "yolo_splits"
            sources.mkdir()
            original_labels = {}
            for name in ("train", "val", "test"):
                paths = [
                    self.create_pair(root / name, "small", "1 0.5 0.5 0.02 0.02\n"),
                    self.create_pair(root / name, "smoke", "0 0.5 0.5 0.2 0.2\n"),
                    self.create_pair(root / name, "empty", ""),
                    self.create_pair(root / name, "invalid", "1 0.5 0.5 0 0\n"),
                ]
                for image in paths:
                    label = image.parent.parent / "labels" / f"{image.stem}.txt"
                    original_labels[label] = label.read_bytes()
                (sources / f"{name}.txt").write_text("\n".join(path.as_posix() for path in paths), encoding="utf-8")
            output = root / "small_fire_v1"
            manifest = build(root, output, {"train": 3, "val": 3, "test": 3}, 42, 0.01)
            for name in ("train", "val", "test"):
                self.assertEqual(len(manifest["excluded_invalid_labels"][name]), 1)
                listing = output / f"{name}.txt"
                self.assertEqual(manifest["selected"][name]["list_sha256"], hashlib.sha256(listing.read_bytes()).hexdigest())
                self.assertTrue(all(Path(path).parent.parent.name == name for path in listing.read_text().splitlines()))
            self.assertEqual(manifest, json.loads((output / "manifest.json").read_text(encoding="utf-8")))
            for path, content in original_labels.items():
                self.assertEqual(path.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
