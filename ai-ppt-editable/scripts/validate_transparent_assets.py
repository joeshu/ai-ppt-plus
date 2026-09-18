#!/usr/bin/env python3
"""Validate final transparent PNG assets and report alpha geometry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def inspect(path: Path, min_padding: int, max_centroid_delta: float) -> dict:
    with Image.open(path) as source:
        native_mode = source.mode
        rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    errors: list[dict] = []
    if native_mode != "RGBA":
        errors.append({"code": "native_rgba_required", "observed": native_mode})
    if bbox is None:
        return {"path": str(path), "valid": False, "errors": [{"code": "empty_alpha"}]}
    left, top, right, bottom = bbox
    padding = [left, top, rgba.width - right, rgba.height - bottom]
    if min(padding) < min_padding:
        errors.append({"code": "unsafe_transparent_padding", "padding": padding, "minimum": min_padding})
    pixels = alpha.load()
    corner_alpha = [pixels[0, 0], pixels[rgba.width - 1, 0], pixels[0, rgba.height - 1], pixels[rgba.width - 1, rgba.height - 1]]
    if any(corner_alpha):
        errors.append({"code": "opaque_corner", "corner_alpha": corner_alpha})
    total = 0
    weighted_x = 0
    weighted_y = 0
    for y in range(rgba.height):
        for x in range(rgba.width):
            weight = pixels[x, y]
            total += weight
            weighted_x += x * weight
            weighted_y += y * weight
    centroid = [weighted_x / total, weighted_y / total]
    canvas_center = [(rgba.width - 1) / 2, (rgba.height - 1) / 2]
    delta_px = [centroid[0] - canvas_center[0], centroid[1] - canvas_center[1]]
    delta_normalized = [delta_px[0] / rgba.width, delta_px[1] / rgba.height]
    if max(abs(delta_normalized[0]), abs(delta_normalized[1])) > max_centroid_delta:
        errors.append({"code": "alpha_centroid_off_center", "delta_normalized": delta_normalized, "maximum": max_centroid_delta})
    coverage = total / (255 * rgba.width * rgba.height)
    return {
        "path": str(path),
        "valid": not errors,
        "native_mode": native_mode,
        "size": [rgba.width, rgba.height],
        "alpha_bbox": list(bbox),
        "transparent_padding": padding,
        "corner_alpha": corner_alpha,
        "alpha_coverage": round(coverage, 6),
        "alpha_centroid": [round(value, 3) for value in centroid],
        "centroid_delta_px": [round(value, 3) for value in delta_px],
        "centroid_delta_normalized": [round(value, 6) for value in delta_normalized],
        "errors": errors,
    }


def validate(asset_dir: Path, min_padding: int = 10, max_centroid_delta: float = 0.08) -> dict:
    paths = sorted(asset_dir.glob("*.png"))
    records = [inspect(path, min_padding, max_centroid_delta) for path in paths]
    errors = [] if paths else [{"code": "no_png_assets", "path": str(asset_dir)}]
    for record in records:
        for error in record["errors"]:
            errors.append({"asset": Path(record["path"]).name, **error})
    return {
        "schema": "ai-ppt-plus/transparent-asset-qa/v1",
        "valid": not errors,
        "asset_dir": str(asset_dir),
        "asset_count": len(records),
        "minimum_padding_px": min_padding,
        "maximum_centroid_delta": max_centroid_delta,
        "assets": records,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--min-padding", type=int, default=10)
    parser.add_argument("--max-centroid-delta", type=float, default=0.08)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.asset_dir.resolve(), args.min_padding, args.max_centroid_delta)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
