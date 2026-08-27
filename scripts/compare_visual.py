#!/usr/bin/env python3
"""Compare a rendered page with its reference image.

The metrics are diagnostics for layout/fidelity regression, not a replacement
for human review. Use `--threshold` only when a project has an approved metric
baseline.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def array(path: Path):
    with Image.open(path) as image:
        image = image.convert("RGB")
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
    rendered, rendered_size = array(Path(args.rendered))
    reference, reference_size = array(Path(args.reference))
    issues = []
    if rendered_size != reference_size:
        issues.append({"severity": "blocker", "code": "dimension_mismatch", "rendered": rendered_size, "reference": reference_size})
    if not issues:
        diff = np.abs(rendered - reference)
        global_ssim = ssim(rendered, reference)
        with Image.open(args.rendered) as r_image, Image.open(args.reference) as s_image:
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
    result = {"schema": "ai-ppt-plus/visual-comparison/v1", "valid": not issues, "rendered": str(Path(args.rendered).resolve()), "reference": str(Path(args.reference).resolve()), "metrics": result_metrics, "issues": issues, "human_visual_review_required": True, "limitation": "metrics are sensitive to font rasterization and do not prove semantic or brand correctness"}
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
