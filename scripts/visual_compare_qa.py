#!/usr/bin/env python3
"""Create visual QA artifacts comparing a source slide to a composed preview.

This script does not decide semantic correctness by itself. It renders the
source and the final PPTX preview into a shared canvas, then writes artifacts
that make placement errors visible for GPT/human visual review:

- side_by_side.png: source on the left, preview on the right
- blend.png: 50/50 overlay
- diff_heatmap.png: red heatmap of pixel differences
- report.json: basic image-difference metrics

Usage:
    python3 scripts/visual_compare_qa.py source.png out/preview/slide_01.png --out-dir qa/visual
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from atomic_output import atomic_write_json
from compare_visual import ASPECT_RATIO_TOLERANCE
from image_viewport import load_viewport


def _die(msg: str, code: int = 2):
    import sys
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _fit_source_to_preview(source, preview_size):
    """Resize a same-aspect source to the preview pixel size."""
    return source.convert("RGB").resize(preview_size)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", help="Original slide image.")
    ap.add_argument("preview", help="Composed PPTX preview image.")
    ap.add_argument("--expected-ratio", type=float, help="optional slide ratio used to validate viewer-capture crops")
    ap.add_argument("--out-dir", required=True, help="Directory for QA artifacts.")
    args = ap.parse_args()

    try:
        from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageStat
    except ImportError:
        _die("Pillow is required (pip install pillow)")

    source_path = Path(args.source)
    preview_path = Path(args.preview)
    out_dir = Path(args.out_dir)
    if not source_path.exists():
        _die(f"source not found: {source_path}")
    if not preview_path.exists():
        _die(f"preview not found: {preview_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    source_image, source_viewport = load_viewport(source_path, expected_ratio=args.expected_ratio)
    preview, preview_viewport = load_viewport(preview_path)
    source_normalized_size = source_image.size
    source_ratio = source_image.width / source_image.height if source_image.height else 0
    if source_viewport["detected"]:
        preview, preview_viewport = load_viewport(preview_path, expected_ratio=source_ratio)
    preview_ratio = preview.width / preview.height if preview.height else 0
    aspect_ratio_delta = abs(source_ratio - preview_ratio)
    if aspect_ratio_delta > ASPECT_RATIO_TOLERANCE:
        _die(
            f"aspect_ratio_mismatch: source {source_image.size} vs preview {preview.size}; "
            "refusing to stretch a visual comparison"
        )
    source = _fit_source_to_preview(source_image, preview.size)

    source.save(out_dir / "source_resized.png")
    preview.save(out_dir / "preview.png")

    side = Image.new("RGB", (preview.width * 2, preview.height), (18, 18, 18))
    side.paste(source, (0, 0))
    side.paste(preview, (preview.width, 0))
    draw = ImageDraw.Draw(side)
    draw.rectangle([0, 0, 170, 32], fill=(0, 0, 0))
    draw.rectangle([preview.width, 0, preview.width + 180, 32], fill=(0, 0, 0))
    draw.text((10, 8), "source", fill=(255, 255, 255))
    draw.text((preview.width + 10, 8), "preview", fill=(255, 255, 255))
    side.save(out_dir / "side_by_side.png")

    blend = Image.blend(source, preview, 0.5)
    blend.save(out_dir / "blend.png")

    diff = ImageChops.difference(source, preview)
    stat = ImageStat.Stat(diff)
    mean_abs = sum(stat.mean) / 3.0
    rms = (sum(v * v for v in stat.rms) / 3.0) ** 0.5

    gray = ImageOps.grayscale(diff)
    hist = gray.histogram()
    total = preview.width * preview.height
    changed_32 = sum(hist[32:]) / total
    changed_64 = sum(hist[64:]) / total

    # Red heatmap over the source. This exposes large content displacement while
    # preserving enough source context to locate the problem.
    heat_alpha = gray.point(lambda v: min(220, int(v * 1.35)))
    heat = Image.new("RGBA", preview.size, (255, 0, 0, 0))
    heat.putalpha(heat_alpha)
    heat_base = source.convert("RGBA")
    heat_base.alpha_composite(heat)
    heat_base.convert("RGB").save(out_dir / "diff_heatmap.png")

    report = {
        "source": str(source_path),
        "preview": str(preview_path),
        "status": "diagnostic",
        "ok": True,
        "source_original_size": source_viewport["original_size"],
        "source_normalized_size": list(source_normalized_size),
        "preview_original_size": preview_viewport["original_size"],
        "preview_size": list(preview.size),
        "resized_for_comparison": tuple(source_normalized_size) != tuple(preview.size),
        "aspect_ratio_delta": round(aspect_ratio_delta, 6),
        "aspect_ratio_tolerance": ASPECT_RATIO_TOLERANCE,
        "viewer_crops": {"source": source_viewport, "preview": preview_viewport},
        "mean_abs_diff_0_255": round(mean_abs, 4),
        "rms_diff_0_255": round(rms, 4),
        "changed_pixel_fraction_threshold_32": round(changed_32, 6),
        "changed_pixel_fraction_threshold_64": round(changed_64, 6),
        "artifacts": {
            "source_resized": str(out_dir / "source_resized.png"),
            "preview": str(out_dir / "preview.png"),
            "side_by_side": str(out_dir / "side_by_side.png"),
            "blend": str(out_dir / "blend.png"),
            "diff_heatmap": str(out_dir / "diff_heatmap.png"),
        },
        "note": (
            "Metrics are diagnostic only. Final pass/fail requires visual review "
            "of source vs preview for text/icon position, size, and overlap."
        ),
    }
    atomic_write_json((out_dir / "report.json").resolve(), report)

    print(f"Wrote {out_dir / 'side_by_side.png'}")
    print(f"Wrote {out_dir / 'blend.png'}")
    print(f"Wrote {out_dir / 'diff_heatmap.png'}")
    print(f"Wrote {out_dir / 'report.json'}")


if __name__ == "__main__":
    main()
