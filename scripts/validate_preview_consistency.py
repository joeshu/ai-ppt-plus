#!/usr/bin/env python3
"""Compare authoring previews with the final renderer output.

Pillow previews are useful for fast authoring feedback, but LibreOffice (or
another declared final renderer) is the visual source of truth.  This gate
keeps the two artifacts comparable and records the difference instead of
allowing a preview to masquerade as final-render evidence.

Usage:
    python3 scripts/validate_preview_consistency.py rendered/ preview/ \
        --expected-pages 3 --require --report preview-consistency.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from atomic_output import atomic_write_json
from compare_visual import ssim


def _page_number(path: Path) -> int | None:
    match = re.search(r"(\d+)$", path.stem)
    return int(match.group(1)) if match else None


def _indexed(directory: Path, *, include_all_pngs: bool = False) -> tuple[dict[int, Path], list[dict[str, Any]]]:
    pages: dict[int, Path] = {}
    issues: list[dict[str, Any]] = []
    if not directory.is_dir():
        return pages, issues
    candidates = sorted(directory.glob("*.png")) if include_all_pngs else sorted(directory.glob("slide*.png"))
    for path in candidates:
        number = _page_number(path)
        if number is None:
            issues.append({"severity": "blocker", "code": "preview_page_number_missing", "path": str(path.resolve())})
            continue
        if number in pages:
            issues.append({"severity": "blocker", "code": "duplicate_page_number", "slide": number, "paths": [str(pages[number].resolve()), str(path.resolve())]})
            continue
        pages[number] = path
    return pages, issues


def _read(path: Path) -> tuple[np.ndarray, tuple[int, int]]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        rgb.load()
        return np.asarray(rgb, dtype=np.float32) / 255.0, rgb.size


def _compare(rendered: Path, preview: Path) -> dict[str, Any]:
    rendered_array, rendered_size = _read(rendered)
    preview_array, preview_size = _read(preview)
    rendered_ratio = rendered_size[0] / rendered_size[1] if rendered_size[1] else 0
    preview_ratio = preview_size[0] / preview_size[1] if preview_size[1] else 0
    if abs(rendered_ratio - preview_ratio) > 0.01:
        return {
            "valid": False,
            "rendered_size": rendered_size,
            "preview_size": preview_size,
            "issues": [{"severity": "blocker", "code": "aspect_ratio_mismatch", "rendered": rendered_size, "preview": preview_size}],
        }
    comparison_size = rendered_size
    if preview_size != comparison_size:
        with Image.open(preview) as image:
            preview_image = image.convert("RGB").resize(comparison_size, Image.Resampling.LANCZOS)
            preview_array = np.asarray(preview_image, dtype=np.float32) / 255.0
    diff = np.abs(rendered_array - preview_array)
    with Image.open(rendered) as rendered_image, Image.open(preview) as preview_image:
        rendered_blur = np.asarray(rendered_image.convert("L").filter(ImageFilter.GaussianBlur(5)), dtype=np.float32) / 255.0
        preview_blur = np.asarray(preview_image.convert("L").resize(comparison_size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(5)), dtype=np.float32) / 255.0
    metrics = {
        "global_ssim": round(ssim(rendered_array, preview_array), 6),
        "blurred_layout_ssim": round(ssim(rendered_blur[..., None], preview_blur[..., None]), 6),
        "mean_absolute_error": round(float(diff.mean()), 6),
        "rmse": round(float(np.sqrt((diff * diff).mean())), 6),
        "pixel_fidelity_score": round(max(0.0, 1.0 - float(diff.mean())), 6),
        "rendered_size": rendered_size,
        "preview_size": preview_size,
        "comparison_size": comparison_size,
        "resized_for_comparison": preview_size != comparison_size,
    }
    return {"valid": True, "metrics": metrics, "issues": []}


def validate(rendered_dir: Path, preview_dir: Path, expected_pages: int, *, require: bool, threshold: float | None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    rendered, rendered_issues = _indexed(rendered_dir)
    preview, preview_issues = _indexed(preview_dir)
    issues.extend(rendered_issues)
    issues.extend(preview_issues)
    expected = set(range(1, expected_pages + 1))
    if expected_pages < 1:
        issues.append({"severity": "blocker", "code": "expected_pages_invalid", "expected_pages": expected_pages})
        expected = set()
    for slide in sorted(expected - set(rendered)):
        issues.append({"severity": "blocker", "code": "final_render_page_missing", "slide": slide})
    if not preview_dir.is_dir() or not preview:
        issue = {"severity": "blocker" if require else "warning", "code": "preview_pages_missing", "path": str(preview_dir.resolve()), "expected_pages": expected_pages}
        (issues if require else warnings).append(issue)
    for slide in sorted(expected - set(preview)):
        issue = {"severity": "blocker" if require else "warning", "code": "preview_page_missing", "slide": slide}
        (issues if require else warnings).append(issue)
    for slide in sorted((set(rendered) | set(preview)) - expected):
        issues.append({"severity": "blocker", "code": "page_outside_expected_range", "slide": slide})

    page_results: list[dict[str, Any]] = []
    for slide in sorted(expected & set(rendered) & set(preview)):
        rendered_path = rendered[slide]
        preview_path = preview[slide]
        try:
            comparison = _compare(rendered_path, preview_path)
        except Exception as exc:
            comparison = {"valid": False, "issues": [{"severity": "blocker", "code": "image_decode_failed", "message": f"{type(exc).__name__}: {exc}"}]}
        page_issues = list(comparison.get("issues", []))
        metrics = comparison.get("metrics", {})
        if threshold is not None and metrics.get("blurred_layout_ssim") is not None and metrics["blurred_layout_ssim"] < threshold:
            page_issues.append({"severity": "blocker", "code": "preview_threshold_not_met", "metric": "blurred_layout_ssim", "threshold": threshold, "observed": metrics["blurred_layout_ssim"]})
        for issue in page_issues:
            issue["slide"] = slide
        issues.extend(page_issues)
        page_results.append({"slide": slide, "rendered": str(rendered_path.resolve()), "preview": str(preview_path.resolve()), "metrics": metrics, "issues": page_issues})

    comparable = [item for item in page_results if item.get("metrics")]
    return {
        "schema": "ai-ppt-plus/preview-consistency-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "rendered_dir": str(rendered_dir.resolve()),
        "preview_dir": str(preview_dir.resolve()),
        "expected_pages": expected_pages,
        "require": require,
        "threshold": threshold,
        "pages": page_results,
        "aggregate": {
            "compared_pages": len(comparable),
            "worst_blurred_layout_ssim": min((item["metrics"]["blurred_layout_ssim"] for item in comparable), default=None),
            "mean_blurred_layout_ssim": round(float(np.mean([item["metrics"]["blurred_layout_ssim"] for item in comparable])), 6) if comparable else None,
            "mean_pixel_fidelity_score": round(float(np.mean([item["metrics"]["pixel_fidelity_score"] for item in comparable])), 6) if comparable else None,
        },
        "issues": issues,
        "warnings": warnings,
        "human_visual_review_required": True,
        "limitation": "the final renderer remains the visual source of truth; preview metrics are diagnostic and do not prove semantic correctness",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered_dir")
    parser.add_argument("preview_dir")
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--require", action="store_true", help="require an exact preview page set")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        result = validate(Path(args.rendered_dir), Path(args.preview_dir), args.expected_pages, require=args.require, threshold=args.threshold)
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/preview-consistency-validation/v1", "valid": False, "status": "invalid", "issues": [{"severity": "blocker", "code": "runtime_error", "message": f"{type(exc).__name__}: {exc}"}], "warnings": []}
    atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
