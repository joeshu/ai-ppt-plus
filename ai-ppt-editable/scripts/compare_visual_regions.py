#!/usr/bin/env python3
"""Score reference fidelity by declared semantic regions.

The region manifest uses normalized ``bbox`` values ``[x, y, w, h]`` in
``0..1``. Each region may declare ``weight`` and ``role``. Background regions
default to a low weight; foreground regions default to 1.0. This report ranks
candidates and attributes weak areas. It complements, but never replaces, the
strict whole-page blocker in ``compare_visual.py``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from atomic_output import atomic_write_json
from compare_visual import sha256, ssim


def load_rgb(path: Path, size=None) -> Image.Image:
    with Image.open(path) as image:
        image = image.convert("RGB")
        if size and image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        return image.copy()


def metrics(candidate: Image.Image, reference: Image.Image) -> dict:
    a = np.asarray(candidate, dtype=np.float32) / 255.0
    b = np.asarray(reference, dtype=np.float32) / 255.0
    diff = np.abs(a - b)
    a_blur = np.asarray(candidate.convert("L").filter(ImageFilter.GaussianBlur(3)), dtype=np.float32) / 255.0
    b_blur = np.asarray(reference.convert("L").filter(ImageFilter.GaussianBlur(3)), dtype=np.float32) / 255.0
    return {
        "global_ssim": round(ssim(a, b), 6),
        "layout_ssim": round(ssim(a_blur[..., None], b_blur[..., None]), 6),
        "pixel_fidelity": round(max(0.0, 1.0 - float(diff.mean())), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate")
    parser.add_argument("reference")
    parser.add_argument("regions")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--report")
    args = parser.parse_args()
    candidate_path, reference_path = Path(args.candidate), Path(args.reference)
    manifest = json.loads(Path(args.regions).read_text(encoding="utf-8"))
    reference = load_rgb(reference_path)
    candidate = load_rgb(candidate_path, reference.size)
    rows, issues = [], []
    weighted_sum = weight_sum = 0.0
    for index, region in enumerate(manifest.get("regions", [])):
        region_id = str(region.get("region_id") or f"region-{index + 1}")
        bbox = region.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            issues.append({"severity": "blocker", "code": "region_bbox_invalid", "region_id": region_id})
            continue
        x, y, w, h = (float(value) for value in bbox)
        if min(x, y, w, h) < 0 or x + w > 1 or y + h > 1 or w <= 0 or h <= 0:
            issues.append({"severity": "blocker", "code": "region_bbox_out_of_bounds", "region_id": region_id})
            continue
        box = (round(x * reference.width), round(y * reference.height), round((x + w) * reference.width), round((y + h) * reference.height))
        row_metrics = metrics(candidate.crop(box), reference.crop(box))
        role = str(region.get("role") or "foreground")
        weight = float(region.get("weight", 0.25 if role == "background" else 1.0))
        score = 0.2 * row_metrics["global_ssim"] + 0.5 * row_metrics["layout_ssim"] + 0.3 * row_metrics["pixel_fidelity"]
        weighted_sum += score * weight
        weight_sum += weight
        rows.append({"region_id": region_id, "role": role, "weight": weight, "bbox": bbox, "score": round(score, 6), "metrics": row_metrics})
    if not rows:
        issues.append({"severity": "blocker", "code": "regions_missing"})
    weighted_score = round(weighted_sum / weight_sum, 6) if weight_sum else 0.0
    if args.threshold is not None and weighted_score < args.threshold:
        issues.append({"severity": "blocker", "code": "foreground_weighted_threshold_not_met", "threshold": args.threshold, "observed": weighted_score})
    result = {
        "schema": "ai-ppt-plus/region-visual-comparison/v1",
        "valid": not issues,
        "candidate": str(candidate_path.resolve()),
        "candidate_sha256": sha256(candidate_path),
        "reference": str(reference_path.resolve()),
        "reference_sha256": sha256(reference_path),
        "foreground_weighted_score": weighted_score,
        "regions": sorted(rows, key=lambda row: row["score"]),
        "issues": issues,
        "human_visual_review_required": True,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
