#!/usr/bin/env python3
"""Run deterministic preflight checks for a reference image and candidate render.

This does not replace visual review. It catches source/sample dimension mix-ups,
aspect-ratio drift, screenshot letterboxing, and obvious blank/black borders so
those artifacts are not misdiagnosed as slide-layout defects.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from atomic_output import atomic_write_json
from image_viewport import detect_viewer_crop


def _die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _stats(path: Path, expected_ratio: float | None = None) -> dict:
    try:
        from PIL import Image, ImageStat
    except ImportError:
        _die("Pillow is required")
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        stat = ImageStat.Stat(rgb)
        # Inspect a 3% edge band. A viewer screenshot may have black bars that
        # are not part of the PPT page; detect them before judging layout.
        band_x, band_y = max(1, int(w * .03)), max(1, int(h * .03))
        bands = [
            rgb.crop((0, 0, band_x, h)), rgb.crop((w-band_x, 0, w, h)),
            rgb.crop((0, 0, w, band_y)), rgb.crop((0, h-band_y, w, h)),
        ]
        dark = 0
        total = 0
        for band in bands:
            # Pillow 14 deprecates getdata(); keep a fallback for older
            # runtimes without adding a noisy warning to every audit.
            if hasattr(band, "get_flattened_data"):
                px = list(band.get_flattened_data())
            else:
                px = list(band.getdata())
            dark += sum(1 for r, g, b in px if max(r, g, b) < 20)
            total += len(px)
        viewer_crop = detect_viewer_crop(rgb, expected_ratio=expected_ratio)
        normalized = rgb.crop(tuple(viewer_crop["crop_box"])) if viewer_crop["detected"] else rgb
        normalized_w, normalized_h = normalized.size
        normalized_stat = ImageStat.Stat(normalized)
        return {
            "size": [w, h],
            "ratio": round(w / h, 7) if h else None,
            "mean_rgb": [round(x, 2) for x in stat.mean],
            "edge_dark_fraction": round(dark / max(1, total), 5),
            "normalized_size": [normalized_w, normalized_h],
            "normalized_ratio": round(normalized_w / normalized_h, 7) if normalized_h else None,
            "normalized_mean_rgb": [round(x, 2) for x in normalized_stat.mean],
            "viewer_crop": viewer_crop,
        }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("reference")
    ap.add_argument("candidate")
    ap.add_argument("--expected-ratio", type=float, default=16 / 9)
    ap.add_argument("--report")
    args = ap.parse_args()
    ref, cand = Path(args.reference), Path(args.candidate)
    if not ref.exists() or not cand.exists():
        _die("reference and candidate must both exist")
    rs = _stats(ref, args.expected_ratio)
    candidate_ratio = rs["normalized_ratio"] or args.expected_ratio
    cs = _stats(cand, candidate_ratio)
    issues = []
    if abs(rs["normalized_ratio"] - args.expected_ratio) > .02:
        issues.append("reference_ratio_unexpected")
    if abs(cs["normalized_ratio"] - args.expected_ratio) > .02:
        issues.append("candidate_ratio_unexpected")
    if cs["edge_dark_fraction"] > .25 and not cs["viewer_crop"]["detected"]:
        issues.append("candidate_may_be_letterboxed_or_have_black_bars")
    result = {
        "schema": "ai-ppt-plus/reference-audit/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "reference": str(ref), "candidate": str(cand),
        "reference_stats": rs, "candidate_stats": cs,
        "issues": issues,
        "human_visual_review_required": True,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
