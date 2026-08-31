#!/usr/bin/env python3
"""Compare every rendered slide with its matching reference image.

Reference and rendered directories must contain files named slide-1.png,
slide-2.png, and so on. The report is a diagnostic evidence layer; it does
not replace human visual review. Same-aspect-ratio pages are normalized to the
reference pixel size; a true aspect-ratio mismatch remains a blocker.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from atomic_output import atomic_write_json
from compare_visual import ASPECT_RATIO_TOLERANCE, ssim
from image_viewport import load_viewport


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_number(path: Path) -> int:
    try:
        return int(path.stem.split("-")[-1])
    except (TypeError, ValueError):
        return 10**9


def parse_pages(value: str | None) -> set[int] | None:
    if not value:
        return None
    selected: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty page selector")
        if "-" in part:
            lo, hi = (int(item.strip()) for item in part.split("-", 1))
            if lo > hi:
                raise ValueError("page range is reversed")
            selected.update(range(lo, hi + 1))
        else:
            selected.add(int(part))
    if not selected or min(selected) < 1:
        raise ValueError("pages must be positive")
    return selected


def compare_page(rendered_path: Path, reference_path: Path, threshold, expected_ratio=None):
    rendered_image, rendered_viewport = load_viewport(rendered_path, expected_ratio=expected_ratio)
    reference_image, reference_viewport = load_viewport(reference_path, expected_ratio=expected_ratio)
    reference_ratio = reference_image.width / reference_image.height if reference_image.height else 0
    if reference_viewport["detected"]:
        rendered_image, rendered_viewport = load_viewport(rendered_path, expected_ratio=reference_ratio)
    rendered_size = rendered_image.size
    reference_size = reference_image.size
    issues = []
    metrics = {}
    resized_for_comparison = False
    if rendered_size != reference_size:
        rendered_ratio = rendered_size[0] / rendered_size[1] if rendered_size[1] else 0
        reference_ratio = reference_size[0] / reference_size[1] if reference_size[1] else 0
        if abs(rendered_ratio - reference_ratio) > ASPECT_RATIO_TOLERANCE:
            issues.append({"severity": "blocker", "code": "aspect_ratio_mismatch", "rendered": rendered_size, "reference": reference_size})
        else:
            resized_for_comparison = True
    if issues:
        return metrics, issues
    if resized_for_comparison:
        rendered_image = rendered_image.resize(reference_size, Image.Resampling.LANCZOS)
    rendered = np.asarray(rendered_image, dtype=np.float32) / 255.0
    reference = np.asarray(reference_image, dtype=np.float32) / 255.0
    diff = np.abs(rendered - reference)
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
        "original_sizes": {"rendered": rendered_viewport["original_size"], "reference": reference_viewport["original_size"]},
        "normalized_sizes": {"rendered": list(rendered_size), "reference": list(reference_size)},
        "viewer_crops": {"rendered": rendered_viewport, "reference": reference_viewport},
    }
    if threshold is not None and metrics["blurred_layout_ssim"] < threshold:
        issues.append({"severity": "blocker", "code": "visual_threshold_not_met", "metric": "blurred_layout_ssim", "threshold": threshold, "observed": metrics["blurred_layout_ssim"]})
    return metrics, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered_dir")
    parser.add_argument("reference_dir")
    parser.add_argument("--expected-pages", type=int, help="expected full-deck page count; missing pages are blockers")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--expected-ratio", type=float, help="optional slide ratio used to validate viewer-capture crops")
    parser.add_argument("--pages", help="only compare selected slide numbers, e.g. 1,3-4")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        selected_pages = parse_pages(args.pages)
    except (TypeError, ValueError) as exc:
        result = {"schema": "ai-ppt-plus/visual-deck-comparison/v1", "valid": False, "rendered_dir": str(Path(args.rendered_dir).resolve()), "reference_dir": str(Path(args.reference_dir).resolve()), "pages": [], "issues": [{"severity": "blocker", "code": "invalid_pages", "message": str(exc)}], "human_visual_review_required": True}
        if args.report:
            report = Path(args.report)
            atomic_write_json(report.resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2
    rendered_dir = Path(args.rendered_dir)
    reference_dir = Path(args.reference_dir)
    rendered_pages = sorted(rendered_dir.glob("slide-*.png"), key=page_number) if rendered_dir.is_dir() else []
    reference_pages = sorted(reference_dir.glob("slide-*.png"), key=page_number) if reference_dir.is_dir() else []
    rendered_by_number = {page_number(path): path for path in rendered_pages}
    reference_by_number = {page_number(path): path for path in reference_pages}
    if selected_pages is not None:
        rendered_by_number = {number: path for number, path in rendered_by_number.items() if number in selected_pages}
        reference_by_number = {number: path for number, path in reference_by_number.items() if number in selected_pages}
    issues = []
    page_results = []
    expected_numbers = None
    if args.expected_pages is not None:
        expected_numbers = set(selected_pages) if selected_pages is not None else set(range(1, args.expected_pages + 1))
        observed_numbers = set(rendered_by_number) | set(reference_by_number)
        for missing in sorted(expected_numbers - observed_numbers):
            issues.append({"severity": "blocker", "code": "page_missing_from_both_directories", "slide": missing})
        for extra in sorted(observed_numbers - expected_numbers):
            issues.append({"severity": "blocker", "code": "page_outside_expected_range", "slide": extra})
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
        metrics, page_issues = compare_page(rendered_path, reference_path, args.threshold, args.expected_ratio)
        for issue in page_issues:
            issue["slide"] = number
        issues.extend(page_issues)
        page_results.append({"slide": number, "rendered": str(rendered_path.resolve()), "rendered_sha256": sha256(rendered_path), "reference": str(reference_path.resolve()), "reference_sha256": sha256(reference_path), "metrics": metrics, "issues": page_issues})
    valid_pages = [item for item in page_results if item["metrics"]]
    result = {
        "schema": "ai-ppt-plus/visual-deck-comparison/v1",
        "valid": not issues,
        "rendered_dir": str(rendered_dir.resolve()),
        "reference_dir": str(reference_dir.resolve()),
        "expected_pages": args.expected_pages if args.expected_pages is not None else len(rendered_pages),
        "reference_pages": len(reference_pages),
        "selected_pages": sorted(selected_pages) if selected_pages is not None else "all",
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
        atomic_write_json(report.resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
