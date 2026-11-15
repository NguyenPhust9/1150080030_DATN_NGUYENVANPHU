from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from ai.evaluate_fire import iou, labels, operating_metrics, validate_output_path


class FireEvaluationTests(SimpleTestCase):
    def test_output_cannot_overwrite_either_input(self):
        model, images = Path("model.pt"), Path("images.txt")
        for output in (model, images, Path(".") / "model.pt"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "overwrite"):
                validate_output_path(output, model, images)
        validate_output_path(Path("report.json"), model, images)

    def test_valid_labels_and_empty_negative_image(self):
        with patch.object(Path, "read_text", return_value="1 0.5 0.5 0.1 0.1\n"):
            parsed = labels(Path("images/frame.jpg"))
        self.assertEqual(parsed[0]["class"], 1)
        with patch.object(Path, "read_text", return_value="\n"):
            self.assertEqual(labels(Path("images/frame.jpg")), [])

    def test_invalid_annotations_fail_before_inference(self):
        invalid = ("0.9 0.5 0.5 0.1 0.1", "2 0.5 0.5 0.1 0.1",
                   "1 nan 0.5 0.1 0.1", "1 0.5 0.5 inf 0.1",
                   "1 0.5 0.5 0 0.1", "1 0.5 0.5 -0.1 0.1",
                   "1 1.1 0.5 0.1 0.1", "1 0.5 0.5 1.1 0.1",
                   "1 0.5 0.5 0.1", "not a label")
        for annotation in invalid:
            with (self.subTest(annotation=annotation),
                  patch.object(Path, "read_text", return_value=annotation),
                  self.assertRaisesRegex(ValueError, "frame.txt:1")):
                labels(Path("images/frame.jpg"))

    def test_iou_handles_disjoint_and_zero_area_boxes(self):
        self.assertEqual(iou([0, 0, 1, 1], [0, 0, 1, 1]), 1)
        self.assertEqual(iou([0, 0, 0, 0], [0, 0, 0, 0]), 0)
        self.assertEqual(iou([0, 0, 0.1, 0.1], [0.5, 0.5, 1, 1]), 0)

    def test_matching_is_one_to_one_and_counts_small_misses_and_negatives(self):
        records = [
            {"labels": [{"class": 1, "xyxy": [0, 0, .05, .05], "small": True},
                        {"class": 1, "xyxy": [.5, .5, .55, .55], "small": True}],
             "predictions": [{"class": 1, "confidence": .9, "xyxy": [0, 0, .05, .05]},
                             {"class": 1, "confidence": .8, "xyxy": [0, 0, .05, .05]}]},
            {"labels": [], "predictions": [{"class": 0, "confidence": .6, "xyxy": [0, 0, 1, 1]}]},
            {"labels": [], "predictions": [{"class": 0, "confidence": .5, "xyxy": [0, 0, 1, 1]}]},
        ]
        result = operating_metrics(records, .25, .55)
        self.assertEqual(result["classes"]["fire"]["tp"], 1)
        self.assertEqual(result["classes"]["fire"]["fp"], 1)
        self.assertEqual(result["classes"]["fire"]["small_recall"], .5)
        self.assertEqual(result["negative_false_alert_rate"], .5)

    def test_wrong_class_cannot_match(self):
        records = [{"labels": [{"class": 1, "xyxy": [0, 0, 1, 1], "small": False}],
                    "predictions": [{"class": 0, "confidence": .9, "xyxy": [0, 0, 1, 1]}]}]
        result = operating_metrics(records, .25, .55)
        self.assertEqual(result["classes"]["fire"]["tp"], 0)
        self.assertEqual(result["classes"]["smoke"]["fp"], 1)
