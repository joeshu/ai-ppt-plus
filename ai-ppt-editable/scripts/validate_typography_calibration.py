#!/usr/bin/env python3
"""Validate measured typography calibration samples.

The input is a small, human/vision-reviewed manifest.  Bboxes are measured
on normalized source and final-render canvases, so this gate catches a title
that is present but materially smaller, wider/narrower, or otherwise using
different font metrics.  It is intentionally separate from pixel SSIM: a
large background can hide a bad text hierarchy in a global score.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/typography-calibration/v1"


def issue(items: list[dict], code: str, **extra) -> None:
    row = {"severity": "blocker", "code": code}
    row.update(extra)
    items.append(row)


def bbox(value) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        numbers = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in numbers):
        return None
    if numbers[0] < 0 or numbers[1] < 0 or numbers[2] <= 0 or numbers[3] <= 0:
        return None
    return numbers


def optional_path(root: Path, value, field: str, issues: list[dict]) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        issue(issues, "path_invalid", field=field)
        return
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        issue(issues, "evidence_file_missing", field=field, path=str(path.resolve()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--max-drift", type=float, default=0.12, help="maximum relative height/width drift before blocking (default: 0.12)")
    parser.add_argument("--report")
    args = parser.parse_args()
    path = Path(args.manifest).resolve()
    issues: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/typography-calibration-validation/v1", "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
        if args.report:
            atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2

    if not isinstance(data, dict):
        issue(issues, "manifest_not_object")
        data = {}
    if data.get("schema") != SCHEMA:
        issue(issues, "schema_invalid", expected=SCHEMA, observed=data.get("schema"))
    coordinate_space = data.get("coordinate_space")
    if coordinate_space != "normalized_pixel":
        issue(issues, "coordinate_space_invalid", expected="normalized_pixel", observed=coordinate_space)
    canvas = data.get("canvas")
    if not isinstance(canvas, dict) or not isinstance(canvas.get("width"), (int, float)) or not isinstance(canvas.get("height"), (int, float)) or canvas.get("width", 0) <= 0 or canvas.get("height", 0) <= 0:
        issue(issues, "canvas_invalid")

    optional_path(path.parent, data.get("reference_image"), "reference_image", issues)
    optional_path(path.parent, data.get("rendered_image"), "rendered_image", issues)
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        issue(issues, "samples_missing_or_empty")
        samples = []
    if not isinstance(args.max_drift, (int, float)) or not 0 <= args.max_drift < 1:
        issue(issues, "max_drift_invalid", observed=args.max_drift)
        max_drift = 0.12
    else:
        max_drift = float(args.max_drift)

    measured: list[dict] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            issue(issues, "sample_not_object", sample_index=index)
            continue
        sample_id = sample.get("sample_id") or sample.get("role") or f"sample-{index + 1}"
        if not isinstance(sample.get("role"), str) or not sample["role"].strip():
            issue(issues, "sample_role_missing", sample_id=sample_id)
        source_box = bbox(sample.get("source_ink_bbox"))
        rendered_box = bbox(sample.get("rendered_ink_bbox"))
        if source_box is None:
            issue(issues, "source_ink_bbox_invalid", sample_id=sample_id)
            continue
        if rendered_box is None:
            issue(issues, "rendered_ink_bbox_invalid", sample_id=sample_id)
            continue
        height_ratio = source_box[3] / rendered_box[3]
        width_ratio = source_box[2] / rendered_box[2]
        metric_scale = (height_ratio + width_ratio) / 2
        drift = max(abs(height_ratio - 1), abs(width_ratio - 1))
        declared_size = sample.get("declared_size_px")
        recommended_size = None
        if isinstance(declared_size, (int, float)) and declared_size > 0:
            recommended_size = round(float(declared_size) * height_ratio, 2)
        row = {
            "sample_id": sample_id,
            "role": sample.get("role"),
            "height_scale_source_over_rendered": round(height_ratio, 4),
            "width_scale_source_over_rendered": round(width_ratio, 4),
            "metric_scale": round(metric_scale, 4),
            "max_relative_drift": round(drift, 4),
            "declared_size_px": declared_size,
            "recommended_size_px": recommended_size,
            "allowed_max_drift": max_drift,
        }
        measured.append(row)
        if drift > max_drift:
            issue(issues, "typography_metric_drift", sample_id=sample_id, role=sample.get("role"), measured=row)

    font_profile = data.get("font_profile")
    warnings: list[dict] = []
    if not isinstance(font_profile, dict):
        warnings.append({"code": "font_profile_missing", "message": "record source/render font families when known; visual review remains required"})
    else:
        if not font_profile.get("render_family"):
            warnings.append({"code": "render_family_missing"})
        if not font_profile.get("source_family"):
            warnings.append({"code": "source_family_unknown"})

    result = {
        "schema": "ai-ppt-plus/typography-calibration-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "manifest": str(path),
        "coordinate_space": coordinate_space,
        "canvas": canvas,
        "sample_count": len(measured),
        "samples": measured,
        "font_profile": font_profile,
        "max_drift": max_drift,
        "warnings": warnings,
        "issues": issues,
        "human_visual_review_required": True,
        "limitation": "bbox calibration catches prominent text metric drift; it does not replace full-slide visual review or semantic text checks",
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

