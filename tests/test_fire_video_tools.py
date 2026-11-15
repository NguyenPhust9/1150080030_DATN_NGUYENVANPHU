"""Local synthetic-video checks. No real camera, database or model loading."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FireVideoExtractionTests(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy as np

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.video = self.directory / "synthetic.avi"
        writer = cv2.VideoWriter(str(self.video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
        self.assertTrue(writer.isOpened())
        try:
            for index in range(12):
                writer.write(np.full((48, 64, 3), index * 15, dtype=np.uint8))
        finally:
            writer.release()
        self.original_hash = hashlib.sha256(self.video.read_bytes()).hexdigest()

    def extract(self, *args):
        return subprocess.run(
            [sys.executable, "-X", "utf8", "ai/inspect_fire_video.py", "--video", str(self.video), *args],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding="utf-8", timeout=15,
        )

    def test_time_range_crop_and_source_preservation(self):
        import cv2

        output = self.directory / "frames"
        result = self.extract("--output", str(output), "--start", ".2", "--end", ".8", "--step", ".2",
                              "--crop", "4", "6", "32", "24")
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([sample["frame"] for sample in manifest["samples"]], [2, 4, 6])
        self.assertEqual(manifest["crop_xywh"], [4, 6, 32, 24])
        self.assertEqual(cv2.imread(str(output / "frame_000002.jpg")).shape[:2], (24, 32))
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).hexdigest(), self.original_hash)
        self.assertEqual(manifest["video_sha256"], self.original_hash)

    def test_existing_output_is_never_overwritten(self):
        result = self.extract("--output", str(self.directory))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("new output directory", result.stderr)
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).hexdigest(), self.original_hash)

    def test_invalid_time_range_and_crop_are_rejected(self):
        for index, arguments in enumerate((
            ("--step", "nan"), ("--step", "0"), ("--start", "inf"),
            ("--start", "1", "--end", ".5"), ("--crop", "63", "0", "10", "10"),
        )):
            output = self.directory / f"invalid-{index}"
            result = self.extract("--output", str(output), *arguments)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
