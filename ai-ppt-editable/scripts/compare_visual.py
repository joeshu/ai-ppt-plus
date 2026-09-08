#!/usr/bin/env python3
"""Compare a rendered page with its reference image.

The metrics are diagnostics for layout/fidelity regression, not a replacement
for human review. Use `--threshold` only when a project has an approved metric
baseline. Same-aspect-ratio images are normalized to the reference pixel size.
A small aspect-ratio delta is tolerated for screenshot capture padding; a true
aspect-ratio mismatch remains a blocker.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from atomic_output import atomic_write_json
from image_viewport import load_viewport


ASPECT_RATIO_TOLERANCE = 0.015
STRICT_DEFAULTS = {
    "blurred_layout_ssim": 0.90,
    "blurred_pixel_fidelity_score": 0.90,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array(path: Path, target_size=None):
    with Image.open(path) as image:
        image = image.convert("RGB")
        if target_size and image.size != tuple(target_size):
            image = image.resize(tuple(target_size), Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.float32) / 255.0, image.size


def raw_image(path: Path):
    """Load an authored slide image without viewer-crop heuristics."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        return image.copy(), {
            "detected": False,
            "crop_box": [0, 0, image.width, image.height],
            "original_size": [image.width, image.height],
            "content_size": [image.width, image.height],
            "original_ratio": round(image.width / image.height, 7) if image.height else None,
            "content_ratio": round(image.width / image.height, 7) if image.height else None,
            "bar_pixels": {"left": 0, "top": 0, "right": 0, "bottom": 0},
            "confidence": 1.0,
            "reason": "raw_slide_canvas",
            "artifact_classification": "authored_slide_canvas",
        }


def ssim(a, b):
    x = a.mean(axis=2)
    y = b.mean(axis=2)
    mu_x, mu_y = x.mean(), y.mean()
    var_x, var_y = x.var(), y.var()
    cov = ((x - mu_x) * (y - mu_y)).mean()
    c1, c2 = 0.0001, 0.0009
    return float(((2 * mu_x * mu_y + c1) * (2 * cov + c2)) / ((mu_x * mu_x + mu_y * mu_y + c1) * (var_x + var_y + c2)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered")
    parser.add_argument("reference")
    parser.add_argument("--expected-ratio", type=float, help="optional slide ratio used to validate viewer-capture crops")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--strict", action="store_true", help="fail closed on reference-fidelity metrics using documented strict defaults")
    parser.add_argument("--min-global-ssim", type=float)
    parser.add_argument("--min-layout-ssim", type=float)
    parser.add_argument("--min-pixel-fidelity", type=float)
    parser.add_argument("--min-blurred-pixel-fidelity", type=float)
    parser.add_argument("--raw-slide", action="store_true", help="compare the complete authored canvases; disable viewer letterbox-crop detection")
    parser.add_argument("--report")
    args = parser.parse_args()
    rendered_path, reference_path = Path(args.rendered), Path(args.reference)
    if args.raw_slide:
        rendered_image, rendered_viewport = raw_image(rendered_path)
        reference_image, reference_viewport = raw_image(reference_path)
    else:
        rendered_image, rendered_viewport = load_viewport(rendered_path)
        reference_image, reference_viewport = load_viewport(
            reference_path,
            expected_ratio=args.expected_ratio,
        )
    # If the caller did not declare a ratio, use the normalized reference
    # viewport as the contract for a viewer-captured candidate as well.
    reference_ratio = reference_image.width / reference_image.height if reference_image.height else 0
    if not args.raw_slide and not args.expected_ratio and reference_viewport["detected"]:
        rendered_image, rendered_viewport = load_viewport(
            rendered_path,
            expected_ratio=reference_ratio,
        )
    rendered_size = rendered_image.size
    reference_size = reference_image.size
    issues = []
    resized_for_comparison = False
    aspect_ratio_delta = 0.0
    if rendered_size != reference_size:
        rendered_ratio = rendered_size[0] / rendered_size[1] if rendered_size[1] else 0
        reference_ratio = reference_size[0] / reference_size[1] if reference_size[1] else 0
        aspect_ratio_delta = abs(rendered_ratio - reference_ratio)
        if aspect_ratio_delta > ASPECT_RATIO_TOLERANCE:
            issues.append({"severity": "blocker", "code": "aspect_ratio_mismatch", "rendered": rendered_size, "reference": reference_size})
        else:
            resized_for_comparison = True
    if resized_for_comparison:
        rendered_image = rendered_image.resize(reference_size, Image.Resampling.LANCZOS)
    rendered = np.asarray(rendered_image, dtype=np.float32) / 255.0
    reference = np.asarray(reference_image, dtype=np.float32) / 255.0
    if not issues:
        diff = np.abs(rendered - reference)
        global_ssim = ssim(rendered, reference)
        blur_radius = 6
        rendered_blur_rgb = np.asarray(rendered_image.filter(ImageFilter.GaussianBlur(blur_radius)), dtype=np.float32) / 255.0
        reference_blur_rgb = np.asarray(reference_image.filter(ImageFilter.GaussianBlur(blur_radius)), dtype=np.float32) / 255.0
        r_blur = rendered_blur_rgb.mean(axis=2)
        s_blur = reference_blur_rgb.mean(axis=2)
        blurred_ssim = ssim(r_blur[..., None], s_blur[..., None])
        blurred_pixel_fidelity = max(0.0, 1.0 - float(np.abs(rendered_blur_rgb - reference_blur_rgb).mean()))
        result_metrics = {
            "global_ssim": round(global_ssim, 6),
            "blurred_layout_ssim": round(blurred_ssim, 6),
            "mean_absolute_error": round(float(diff.mean()), 6),
            "rmse": round(float(np.sqrt((diff * diff).mean())), 6),
            "pixel_fidelity_score": round(max(0.0, 1.0 - float(diff.mean())), 6),
            "blurred_pixel_fidelity_score": round(blurred_pixel_fidelity, 6),
            "layout_blur_radius": blur_radius,
        }
        thresholds = {
            "global_ssim": args.min_global_ssim,
            "blurred_layout_ssim": args.min_layout_ssim if args.min_layout_ssim is not None else args.threshold,
            "pixel_fidelity_score": args.min_pixel_fidelity,
            "blurred_pixel_fidelity_score": args.min_blurred_pixel_fidelity,
        }
        if args.strict:
            thresholds = {key: value if value is not None else STRICT_DEFAULTS.get(key) for key, value in thresholds.items()}
        for metric, threshold in thresholds.items():
            if threshold is not None and result_metrics[metric] < threshold:
                issues.append({"severity": "blocker", "code": "visual_threshold_not_met", "metric": metric, "threshold": threshold, "observed": result_metrics[metric]})
    else:
        result_metrics = {}
    result = {"schema": "ai-ppt-plus/visual-comparison/v1", "valid": not issues, "rendered": str(rendered_path.resolve()), "rendered_sha256": sha256(rendered_path), "reference": str(reference_path.resolve()), "reference_sha256": sha256(reference_path), "original_sizes": {"rendered": rendered_viewport["original_size"], "reference": reference_viewport["original_size"]}, "normalized_sizes": {"rendered": list(rendered_size), "reference": list(reference_size)}, "viewer_crops": {"rendered": rendered_viewport, "reference": reference_viewport}, "aspect_ratio_delta": round(aspect_ratio_delta, 6), "aspect_ratio_tolerance": ASPECT_RATIO_TOLERANCE, "comparison_size": list(reference_size if resized_for_comparison else rendered_size), "resized_for_comparison": resized_for_comparison, "metrics": result_metrics, "issues": issues, "human_visual_review_required": True, "limitation": "metrics are sensitive to font rasterization and do not prove semantic or brand correctness"}
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(report.resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
