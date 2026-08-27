#!/usr/bin/env python3
"""Compare every rendered slide with its matching reference image.

Reference and rendered directories must contain files named slide-1.png,
slide-2.png, and so on. The report is a diagnostic evidence layer; it does
not replace human visual review. Same-aspect-ratio pages are normalized to the
reference pixel size; a true aspect-ratio mismatch remains a blocker.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from compare_visual import array, ssim


def page_number(path: Path) -> int:
    try:
        return int(path.stem.split("-")[-1])
    except (TypeError, ValueError):
        return 10**9


def compare_page(rendered_path: Path, reference_path: Path, threshold):
    _, rendered_size = array(rendered_path)
    _, reference_size = array(reference_path)
    issues = []
    metrics = {}
    resized_for_comparison = False
    if rendered_size != reference_size:
        rendered_ratio = rendered_size[0] / rendered_size[1] if rendered_size[1] else 0
        reference_ratio = reference_size[0] / reference_size[1] if reference_size[1] else 0
        if abs(rendered_ratio - reference_ratio) > 0.01:
            issues.append({"severity": "blocker", "code": "aspect_ratio_mismatch", "rendered": rendered_size, "reference": reference_size})
        else:
            resized_for_comparison = True
    if issues:
        return metrics, issues
    rendered, _ = array(rendered_path, reference_size if resized_for_comparison else None)
    reference, _ = array(reference_path)
    diff = np.abs(rendered - reference)
    with Image.open(rendered_path) as rendered_image, Image.open(reference_path) as reference_image:
        if resized_for_comparison:
            rendered_image = rendered_image.convert("RGB").resize(reference_size, Image.Resampling.LANCZOS)
        rendered_blur = np.asarray(rendered_image.convert("L").filter(ImageFilter.GaussianBlur(5)), dtype=np.float32) / 255.0
        reference_blur = np.asarray(reference_image.convert("L").filter(ImageFilter.GaussianBlur(5)), dtype=np.float32) / 255.0
    metrics = {
        "global_ssim": round(ssim(rendered, reference), 6),
        "blurred_layout_ssim": round(ssim(rendered_blur[..., None], reference_blur[..., None]), 6),
        "mean_absolute_error": round(float(diff.mean()), 6),
        "rmse": round(float(np.sqrt((diff * diff).mean())), 6),
        "pixel_fidelity_score": round(max(0.0, 1.0 - float(diff.mean())), 6),
        "resized_for_comparison": resized_for_comparison,
        "comparison_size": reference_size if resized_for_comparison else rendered_size,
    }
    if threshold is not None and metrics["blurred_layout_ssim"] < threshold:
        issues.append({"severity": "blocker", "code": "visual_threshold_not_met", "metric": "blurred_layout_ssim", "threshold": threshold, "observed": metrics["blurred_layout_ssim"]})
    return metrics, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered_dir")
    parser.add_argument("reference_dir")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--report")
    args = parser.parse_args()
    rendered_dir = Path(args.rendered_dir)
    reference_dir = Path(args.reference_dir)
    rendered_pages = sorted(rendered_dir.glob("slide-*.png"), key=page_number) if rendered_dir.is_dir() else []
    reference_pages = sorted(reference_dir.glob("slide-*.png"), key=page_number) if reference_dir.is_dir() else []
    rendered_by_number = {page_number(path): path for path in rendered_pages}
    reference_by_number = {page_number(path): path for path in reference_pages}
    issues = []
    page_results = []
    all_numbers = sorted(set(rendered_by_number) | set(reference_by_number))
    for number in all_numbers:
        rendered_path = rendered_by_number.get(number)
        reference_path = reference_by_number.get(number)
        if rendered_path is None:
            issues.append({"severity": "blocker", "code": "rendered_page_missing", "slide": number, "reference": str(reference_path.resolve())})
            continue
        if reference_path is None:
            issues.append({"severity": "blocker", "code": "reference_page_missing", "slide": number, "rendered": str(rendered_path.resolve())})
            continue
        metrics, page_issues = compare_page(rendered_path, reference_path, args.threshold)
        for issue in page_issues:
            issue["slide"] = number
        issues.extend(page_issues)
        page_results.append({"slide": number, "rendered": str(rendered_path.resolve()), "reference": str(reference_path.resolve()), "metrics": metrics, "issues": page_issues})
    valid_pages = [item for item in page_results if item["metrics"]]
    result = {
        "schema": "ai-ppt-plus/visual-deck-comparison/v1",
        "valid": not issues,
        "rendered_dir": str(rendered_dir.resolve()),
        "reference_dir": str(reference_dir.resolve()),
        "expected_pages": len(rendered_pages),
        "reference_pages": len(reference_pages),
        "pages": page_results,
        "aggregate": {
            "compared_pages": len(valid_pages),
            "worst_blurred_layout_ssim": min((item["metrics"]["blurred_layout_ssim"] for item in valid_pages), default=None),
            "mean_blurred_layout_ssim": round(float(np.mean([item["metrics"]["blurred_layout_ssim"] for item in valid_pages])), 6) if valid_pages else None,
            "mean_pixel_fidelity_score": round(float(np.mean([item["metrics"]["pixel_fidelity_score"] for item in valid_pages])), 6) if valid_pages else None,
        },
        "issues": issues,
        "human_visual_review_required": True,
        "limitation": "metrics are sensitive to font rasterization and do not prove semantic or brand correctness",
    }
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
