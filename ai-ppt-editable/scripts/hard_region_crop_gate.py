#!/usr/bin/env python3
"""Measure key-region local fidelity as render/repair diagnostics.

Regional SSIM and pixel fidelity rank repair work. They never independently
block normal fixed-reference production. Missing/invalid region evidence can
still fail because the short loop requires same-coordinate crop evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from skimage.metrics import structural_similarity as ssim

PROFILES = ("standard", "dense_editable", "gradient", "complex_illustration", "competitive_ab")


def _box_px(box, width, height):
    x, y, w, h = [float(v) for v in box]
    if max(abs(x), abs(y), abs(w), abs(h)) <= 1.5:
        x, w = x * width, w * width
        y, h = y * height, h * height
    x0 = max(0, min(width - 1, int(round(x))))
    y0 = max(0, min(height - 1, int(round(y))))
    x1 = max(x0 + 1, min(width, int(round(x + w))))
    y1 = max(y0 + 1, min(height, int(round(y + h))))
    return x0, y0, x1, y1


def _score(a: Image.Image, b: Image.Image) -> dict:
    if b.size != a.size:
        b = b.resize(a.size, Image.Resampling.LANCZOS)
    aa, bb = np.asarray(a.convert("RGB")), np.asarray(b.convert("RGB"))
    raw = float(ssim(aa, bb, channel_axis=2, data_range=255))
    ba = np.asarray(a.filter(ImageFilter.GaussianBlur(3)).convert("RGB"))
    bb2 = np.asarray(b.filter(ImageFilter.GaussianBlur(3)).convert("RGB"))
    layout = float(ssim(ba, bb2, channel_axis=2, data_range=255))
    pixel = float(1.0 - np.abs(ba.astype(np.float32) - bb2.astype(np.float32)).mean() / 255.0)
    return {"ssim": raw, "layout_ssim": layout, "pixel_fidelity": pixel}


def evaluate(source: Image.Image, candidate: Image.Image, spec: dict, output_dir: Path, *, profile: str = "standard") -> dict:
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile}")
    source = source.convert("RGB")
    candidate = candidate.convert("RGB").resize(source.size, Image.Resampling.LANCZOS)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, region in enumerate(spec.get("regions") or [], 1):
        rid = str(region.get("id") or f"region-{index}")
        box = _box_px(region["bbox"], *source.size)
        src = source.crop(box)
        cand = candidate.crop(box)
        scores = _score(src, cand)
        min_layout = float(region.get("min_layout_ssim", 0.90))
        min_pixel = float(region.get("min_pixel_fidelity", 0.90))
        diagnostic_pass = scores["layout_ssim"] >= min_layout and scores["pixel_fidelity"] >= min_pixel
        src_path = output_dir / f"{index:02d}-{rid}-source.png"
        cand_path = output_dir / f"{index:02d}-{rid}-candidate.png"
        src.save(src_path)
        cand.save(cand_path)
        rows.append({
            "id": rid,
            "bbox_px": list(box),
            "scores": scores,
            "thresholds": {"layout_ssim": min_layout, "pixel_fidelity": min_pixel},
            "absolute_threshold_applied": False,
            "absolute_threshold_pass": diagnostic_pass,
            "valid": True,
            "diagnostic_only": True,
            "source_crop": str(src_path),
            "candidate_crop": str(cand_path),
            "repair_trace": [] if diagnostic_pass else ["local_crop"],
        })
    diagnostic_failures = [row for row in rows if not row["absolute_threshold_pass"]]
    worst = min(
        rows,
        key=lambda row: min(
            row["scores"]["layout_ssim"] - row["thresholds"]["layout_ssim"],
            row["scores"]["pixel_fidelity"] - row["thresholds"]["pixel_fidelity"],
        ),
    ) if rows else None
    valid = bool(rows)
    return {
        "schema": "ai-ppt-plus/hard-region-crop-gate/v2",
        "profile": profile,
        "gate_mode": "repair_diagnostic",
        "valid": valid,
        "region_count": len(rows),
        "failure_count": 0 if valid else 1,
        "diagnostic_absolute_failure_count": len(diagnostic_failures),
        "repair_loop_required": bool(diagnostic_failures),
        "repair_signals": [
            {"region_id": row["id"], "code": "regional_fidelity_below_target", "scores": row["scores"], "targets": row["thresholds"], "diagnostic_only": True}
            for row in diagnostic_failures
        ],
        "worst_region": worst["id"] if worst else None,
        "regions": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--regions", type=Path, required=True, help="JSON with regions[{id,bbox,min_layout_ssim,min_pixel_fidelity}]")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--profile", choices=PROFILES, default="standard")
    args = parser.parse_args()
    source = Image.open(args.source)
    candidate = Image.open(args.candidate)
    spec = json.loads(args.regions.read_text(encoding="utf-8"))
    report = evaluate(source, candidate, spec, args.output_dir, profile=args.profile)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("schema", "profile", "gate_mode", "valid", "region_count", "failure_count", "diagnostic_absolute_failure_count", "repair_loop_required", "worst_region")}, ensure_ascii=False))
    return 0 if report["valid"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
