#!/usr/bin/env python3
"""Compare a rendered page with its reference image.

The metrics are diagnostics for layout/fidelity regression, not a replacement
for human review. Use `--threshold` only when a project has an approved metric
baseline. Same-aspect-ratio images are normalized to the reference pixel size;
a true aspect-ratio mismatch remains a blocker.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from atomic_output import atomic_write_json


def array(path: Path, target_size=None):
    with Image.open(path) as image:
        image = image.convert("RGB")
        if target_size and image.size != tuple(target_size):
            image = image.resize(tuple(target_size), Image.Resampling.LANCZOS)
        return np.asarray(image, dtype=np.float32) / 255.0, image.size


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
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--report")
    args = parser.parse_args()
    rendered_path, reference_path = Path(args.rendered), Path(args.reference)
    _, rendered_size = array(rendered_path)
    _, reference_size = array(reference_path)
    issues = []
    resized_for_comparison = False
    if rendered_size != reference_size:
        rendered_ratio = rendered_size[0] / rendered_size[1] if rendered_size[1] else 0
        reference_ratio = reference_size[0] / reference_size[1] if reference_size[1] else 0
        if abs(rendered_ratio - reference_ratio) > 0.01:
            issues.append({"severity": "blocker", "code": "aspect_ratio_mismatch", "rendered": rendered_size, "reference": reference_size})
        else:
            resized_for_comparison = True
    rendered, _ = array(rendered_path, reference_size if resized_for_comparison else None)
    reference, _ = array(reference_path)
    if not issues:
        diff = np.abs(rendered - reference)
        global_ssim = ssim(rendered, reference)
        with Image.open(rendered_path) as r_image, Image.open(reference_path) as s_image:
            if resized_for_comparison:
                r_image = r_image.convert("RGB").resize(reference_size, Image.Resampling.LANCZOS)
            r_blur = np.asarray(r_image.convert("L").filter(ImageFilter.GaussianBlur(5)), dtype=np.float32) / 255.0
            s_blur = np.asarray(s_image.convert("L").filter(ImageFilter.GaussianBlur(5)), dtype=np.float32) / 255.0
        blurred_ssim = ssim(r_blur[..., None], s_blur[..., None])
        result_metrics = {
            "global_ssim": round(global_ssim, 6),
            "blurred_layout_ssim": round(blurred_ssim, 6),
            "mean_absolute_error": round(float(diff.mean()), 6),
            "rmse": round(float(np.sqrt((diff * diff).mean())), 6),
            "pixel_fidelity_score": round(max(0.0, 1.0 - float(diff.mean())), 6),
        }
        if args.threshold is not None and result_metrics["blurred_layout_ssim"] < args.threshold:
            issues.append({"severity": "blocker", "code": "visual_threshold_not_met", "metric": "blurred_layout_ssim", "threshold": args.threshold, "observed": result_metrics["blurred_layout_ssim"]})
    else:
        result_metrics = {}
    result = {"schema": "ai-ppt-plus/visual-comparison/v1", "valid": not issues, "rendered": str(rendered_path.resolve()), "reference": str(reference_path.resolve()), "original_sizes": {"rendered": rendered_size, "reference": reference_size}, "comparison_size": reference_size if resized_for_comparison else rendered_size, "resized_for_comparison": resized_for_comparison, "metrics": result_metrics, "issues": issues, "human_visual_review_required": True, "limitation": "metrics are sensitive to font rasterization and do not prove semantic or brand correctness"}
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(report.resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
