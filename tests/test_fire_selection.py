import unittest
from copy import deepcopy

from ai.select_fire_candidate import select_candidate


def point(threshold=0.25, small=0.6, precision=0.8, recall=0.75, negative_alerts=2):
    # Large synthetic denominators preserve the requested four-decimal boundary
    # values while ensuring all reported metrics have integer-count evidence.
    gt, small_gt = 100000, 10000
    tp, small_tp = round(recall * gt), round(small * small_gt)
    fp = round(tp / precision - tp)
    return {
        "fire_threshold": threshold, "smoke_threshold": 0.55,
        "negative_images": 100, "negative_false_alert_images": negative_alerts,
        "classes": {
            "fire": {"precision": round(tp / (tp + fp), 4), "recall": recall, "small_recall": small,
                     "tp": tp, "fp": fp, "gt": gt, "small_tp": small_tp, "small_gt": small_gt},
            "smoke": {"precision": 0.8, "recall": 0.7, "small_recall": 0.5,
                      "tp": 280, "fp": 70, "gt": 400, "small_tp": 10, "small_gt": 20},
        },
    }


def report(*points, model="baseline", size=768):
    return {
        "model": model + ".pt", "model_sha256": model,
        "images_sha256": "validation-list-sha", "images": 400,
        "imgsz": size, "iou": 0.5, "small_area_ratio": 0.01,
        "operating_points": list(points) or [point()],
        "records": [{"path": f"image-{index}.jpg", "predictions": [None] * 52 if index == 0 else []}
                    for index in range(400)],
    }


class FireSelectionTests(unittest.TestCase):
    def test_accepts_guard_boundary_and_keeps_input_unchanged(self):
        candidate = report(point(small=0.62, precision=0.78, recall=0.73, negative_alerts=3), model="new")
        before = deepcopy(candidate)
        result = select_candidate(report(), candidate)
        self.assertTrue(result["accepted"], result)
        self.assertEqual(candidate, before)
        self.assertEqual(result["candidate"]["model_sha256"], "new")
        self.assertEqual(result["inference_limits"]["baseline"]["max_det"], 100)
        self.assertEqual(result["inference_limits"]["baseline"]["maximum_observed_detections"], 52)

    def test_rejects_small_fire_non_improvement(self):
        result = select_candidate(report(), report(point(small=0.6199), model="new"))
        self.assertFalse(result["accepted"])
        self.assertIn("small_fire_recall", str(result["operating_point_checks"]))

    def test_reference_guards_against_resolution_regression(self):
        result = select_candidate(report(), report(point(small=0.7, precision=0.82), model="new"),
                                  report(point(precision=0.9), size=512))
        self.assertFalse(result["accepted"])
        self.assertIn("fire.precision", str(result["operating_point_checks"]))

    def test_rejects_wrong_image_list_resolution_or_matching_schema(self):
        for key, value in (("images_sha256", "test-list-sha"), ("imgsz", 512), ("iou", 0.4), ("small_area_ratio", 0.02)):
            candidate = report(point(small=0.7), model="new")
            candidate[key] = value
            with self.subTest(key=key):
                self.assertFalse(select_candidate(report(), candidate)["accepted"])

    def test_rejects_bad_smoke_threshold_or_counts_or_more_false_alarms(self):
        for key, value in (("smoke_threshold", 0.5), ("negative_images", 99), ("negative_false_alert_images", 4)):
            candidate_point = point(small=0.7)
            candidate_point[key] = value
            with self.subTest(key=key):
                self.assertFalse(select_candidate(report(), report(candidate_point, model="new"))["accepted"])

    def test_smoke_regression_is_not_hidden_by_fire_gain(self):
        candidate_point = point(small=0.8)
        candidate_point["classes"]["smoke"]["recall"] = 0.67
        self.assertFalse(select_candidate(report(), report(candidate_point, model="new"))["accepted"])

    def test_ties_prefer_precision_then_conservative_threshold(self):
        candidate = report(point(0.15, small=0.7, precision=0.8), point(0.2, small=0.7, precision=0.85),
                           point(0.3, small=0.7, precision=0.85), model="new")
        result = select_candidate(report(), candidate)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["selected_operating_point"]["fire_threshold"], 0.3)

    def test_rejects_potentially_truncated_reports(self):
        candidate = report(point(small=0.7), model="new")
        candidate["prediction_max_det"] = 50
        result = select_candidate(report(), candidate)
        self.assertFalse(result["accepted"])
        self.assertIn("max_det", str(result["fail_reasons"]))

    def test_reference_must_be_same_baseline_checkpoint(self):
        result = select_candidate(report(), report(point(small=0.7), model="new"), report(model="unrelated", size=512))
        self.assertFalse(result["accepted"])

    def test_rejects_metrics_that_disagree_with_counts(self):
        candidate = report(point(small=0.7), model="new")
        candidate["operating_points"][0]["classes"]["fire"]["small_recall"] = 0.9
        result = select_candidate(report(), candidate)
        self.assertFalse(result["accepted"])
        self.assertIn("disagrees with detection counts", str(result))

    def test_rejects_impossible_detection_counts(self):
        candidate = report(point(small=0.7), model="new")
        candidate["operating_points"][0]["classes"]["fire"]["small_tp"] = 100001
        self.assertFalse(select_candidate(report(), candidate)["accepted"])

    def test_rejects_missing_duplicate_and_different_record_paths(self):
        for operation in ("missing", "duplicate", "different"):
            candidate = report(point(small=0.7), model="new")
            if operation == "missing":
                candidate["records"].pop()
            elif operation == "duplicate":
                candidate["records"][0]["path"] = candidate["records"][1]["path"]
            else:
                candidate["records"][0]["path"] = "other-image.jpg"
            with self.subTest(operation=operation):
                self.assertFalse(select_candidate(report(), candidate)["accepted"])


if __name__ == "__main__":
    unittest.main()
