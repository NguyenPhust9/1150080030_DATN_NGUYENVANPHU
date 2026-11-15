"""Select a fire checkpoint operating point using VALIDATION reports only.

This tool reads JSON and writes a decision artifact. It never loads a model or
changes environment variables, active weights, databases, or camera settings.
The caller must supply validation reports; a report hash cannot prove its split.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

BASE_FIRE_THRESHOLD = 0.25
SMOKE_THRESHOLD = 0.55
MIN_SMALL_FIRE_GAIN = 0.02
MAX_METRIC_REGRESSION = 0.02
EXTRA_NEGATIVE_ALERTS_PER_100 = 1


def baseline_point(report: dict) -> dict:
    matches = [point for point in report["operating_points"]
               if math.isclose(point["fire_threshold"], BASE_FIRE_THRESHOLD)
               and math.isclose(point["smoke_threshold"], SMOKE_THRESHOLD)]
    if len(matches) != 1:
        raise ValueError("Baseline/reference must contain exactly one fire=0.25, smoke=0.55 operating point")
    return matches[0]


def checkpoint(report: dict) -> dict:
    return {name: report.get(name) for name in ("model", "model_sha256", "images_sha256", "images", "imgsz")}


def validate_point(point: dict, base: dict) -> None:
    for label in ("fire", "smoke"):
        current, original = point["classes"][label], base["classes"][label]
        for name in ("tp", "fp", "gt", "small_tp", "small_gt"):
            value = current[name]
            if type(value) is not int or value < 0:
                raise ValueError(f"Invalid {label}.{name} count")
        if (current["tp"] > current["gt"] or current["small_gt"] > current["gt"]
                or current["small_tp"] > min(current["small_gt"], current["tp"])):
            raise ValueError(f"Inconsistent {label} detection counts")
        expected = {
            "precision": round(current["tp"] / max(1, current["tp"] + current["fp"]), 4),
            "recall": round(current["tp"] / max(1, current["gt"]), 4),
            "small_recall": round(current["small_tp"] / max(1, current["small_gt"]), 4),
        }
        for metric in ("precision", "recall", "small_recall"):
            value = current[metric]
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Invalid {label}.{metric}")
            if not math.isclose(value, expected[metric], rel_tol=0, abs_tol=1e-12):
                raise ValueError(f"{label}.{metric} disagrees with detection counts")
        if current["gt"] != original["gt"] or current["small_gt"] != original["small_gt"]:
            raise ValueError(f"Ground-truth counts differ for {label}")
        if current["gt"] <= 0:
            raise ValueError(f"Validation has no ground-truth {label} boxes")
    if point["classes"]["fire"]["small_gt"] <= 0:
        raise ValueError("Validation has no small-fire ground truth")
    negatives = point["negative_images"]
    alerts = point["negative_false_alert_images"]
    if type(negatives) is not int or negatives != base["negative_images"] or negatives <= 0:
        raise ValueError("Negative-image counts differ or are empty")
    if type(alerts) is not int or not 0 <= alerts <= negatives:
        raise ValueError("Invalid negative false-alert count")
    if "negative_false_alert_rate" in point and not math.isclose(
        point["negative_false_alert_rate"], round(alerts / negatives, 4), rel_tol=0, abs_tol=1e-12
    ):
        raise ValueError("Negative false-alert rate disagrees with image counts")
    for name in ("fire_threshold", "smoke_threshold"):
        value = point[name]
        if not math.isfinite(value) or not 0 < value <= 1:
            raise ValueError(f"Invalid {name}")


def select_candidate(baseline: dict, candidate: dict, reference: dict | None = None) -> dict:
    decision = {
        "purpose": "validation_only_checkpoint_and_threshold_selection",
        "accepted": False,
        "baseline": checkpoint(baseline),
        "reference": checkpoint(reference) if reference else None,
        "candidate": checkpoint(candidate),
        "selected_operating_point": None,
        "guard": {
            "baseline_fire_threshold": BASE_FIRE_THRESHOLD,
            "smoke_threshold": SMOKE_THRESHOLD,
            "minimum_small_fire_recall_gain": MIN_SMALL_FIRE_GAIN,
            "maximum_precision_recall_regression": MAX_METRIC_REGRESSION,
            "extra_negative_alerts_per_100": EXTRA_NEGATIVE_ALERTS_PER_100,
        },
        "fail_reasons": [],
        "operating_point_checks": [],
        "warnings": [
            "The caller must verify these are validation reports, not held-out test reports.",
            "Metrics describe independent images, not temporal webcam alert performance.",
            "This decision does not deploy or change any active configuration.",
        ],
        "inference_limits": {},
    }
    try:
        if not baseline.get("images_sha256") or not baseline.get("model_sha256") or not candidate.get("model_sha256"):
            raise ValueError("Missing image-list or checkpoint hashes")
        if baseline["imgsz"] != candidate["imgsz"] or candidate["imgsz"] != 768:
            raise ValueError("Baseline and candidate must both be evaluated at imgsz=768")
        reports = {"baseline": baseline, "candidate": candidate}
        if reference:
            reports["reference"] = reference
            if reference.get("model_sha256") != baseline["model_sha256"]:
                raise ValueError("Reference must evaluate the same baseline checkpoint")
        for name, report in reports.items():
            if type(report["images"]) is not int or report["images"] <= 0:
                raise ValueError(f"{name}: invalid image count")
            if report["images_sha256"] != baseline["images_sha256"] or report["images"] != baseline["images"]:
                raise ValueError(f"{name}: image lists/counts differ")
            records = report.get("records")
            if not isinstance(records, list) or len(records) != report["images"]:
                raise ValueError(f"{name}: record count disagrees with image count")
            record_paths = [row.get("path") for row in records]
            if (any(not isinstance(path, str) or not path for path in record_paths)
                    or len(set(record_paths)) != len(record_paths)):
                raise ValueError(f"{name}: records have missing or duplicate image paths")
            if name != "baseline" and set(record_paths) != {row["path"] for row in baseline["records"]}:
                raise ValueError(f"{name}: evaluated image paths differ")
            if report["iou"] != 0.5 or report["small_area_ratio"] != 0.01:
                raise ValueError(f"{name}: expected IoU=0.5 and small_area_ratio=0.01")
            if report.get("prediction_confidence_floor", 0.05) != 0.05 or report.get("prediction_nms_iou", 0.7) != 0.7:
                raise ValueError(f"{name}: incompatible inference confidence floor or NMS IoU")
            legacy = "prediction_max_det" not in report
            limit = report.get("prediction_max_det", 100)
            observed = max((len(row["predictions"]) for row in report.get("records", [])), default=None)
            decision["inference_limits"][name] = {
                "max_det": limit, "legacy_inferred": legacy,
                "maximum_observed_detections": observed,
            }
            if legacy:
                decision["warnings"].append(f"{name}: legacy report lacks max_det metadata; known legacy evaluator used max_det=100.")
            if observed is not None and observed >= limit:
                raise ValueError(f"{name}: prediction count reached max_det; rerun with a higher limit")
        limits = {item["max_det"] for item in decision["inference_limits"].values()}
        if len(limits) > 1:
            decision["warnings"].append("Reports use different max_det limits; inspect maximum_observed_detections to confirm neither was truncated.")
        base = baseline_point(baseline)
        reference_point = baseline_point(reference) if reference else base
        validate_point(base, base)
        validate_point(reference_point, base)
        if base["negative_images"] > baseline["images"]:
            raise ValueError("Negative-image count exceeds evaluated image count")
        floors = {
            label: {metric: max(base["classes"][label][metric], reference_point["classes"][label][metric]) - MAX_METRIC_REGRESSION
                    for metric in ("precision", "recall")}
            for label in ("fire", "smoke")
        }
        small_floor = base["classes"]["fire"]["small_recall"] + MIN_SMALL_FIRE_GAIN
        negative_ceiling = base["negative_false_alert_images"] + base["negative_images"] * EXTRA_NEGATIVE_ALERTS_PER_100 / 100
        decision["required_metrics"] = {
            "small_fire_recall_minimum": small_floor,
            "class_metric_minimums": floors,
            "negative_false_alert_images_maximum": negative_ceiling,
        }
        feasible = []
        for point in candidate["operating_points"]:
            reasons = []
            try:
                validate_point(point, base)
                if not math.isclose(point["smoke_threshold"], SMOKE_THRESHOLD):
                    reasons.append("smoke_threshold must equal 0.55")
                if point["fire_threshold"] < candidate.get("prediction_confidence_floor", 0.05):
                    reasons.append("fire_threshold is below recorded inference confidence floor")
                if point["classes"]["fire"]["small_recall"] + 1e-12 < small_floor:
                    reasons.append("small_fire_recall gain is below 0.02")
                for label in ("fire", "smoke"):
                    for metric, floor in floors[label].items():
                        if point["classes"][label][metric] + 1e-12 < floor:
                            reasons.append(f"{label}.{metric} regressed by more than 0.02")
                if point["negative_false_alert_images"] > negative_ceiling:
                    reasons.append("negative false-alert images exceed the allowed increase")
            except (KeyError, TypeError, ValueError) as exc:
                reasons.append(f"Invalid operating point: {exc}")
            decision["operating_point_checks"].append({
                "fire_threshold": point.get("fire_threshold"),
                "smoke_threshold": point.get("smoke_threshold"),
                "accepted": not reasons, "fail_reasons": reasons,
            })
            if not reasons:
                feasible.append(point)
        if feasible:
            # Highest recall, then precision, then the more conservative threshold.
            chosen = max(feasible, key=lambda point: (
                point["classes"]["fire"]["small_recall"],
                point["classes"]["fire"]["precision"], point["fire_threshold"],
            ))
            decision["accepted"] = True
            decision["selected_operating_point"] = chosen
        else:
            decision["fail_reasons"].append("No candidate validation operating point satisfies every predeclared guard.")
    except (KeyError, TypeError, ValueError) as exc:
        decision["fail_reasons"].append(f"Reports are not comparable: {exc}")
    return decision


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {name: getattr(args, name) for name in ("baseline", "reference", "candidate")}
    if args.output.resolve() in {path.resolve() for path in paths.values() if path}:
        parser.error("Output must not overwrite an input report")
    reports = {name: json.loads(path.read_text(encoding="utf-8")) if path else None for name, path in paths.items()}
    decision = select_candidate(**reports)
    decision["report_paths"] = {name: str(path.resolve()) if path else None for name, path in paths.items()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(decision, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
