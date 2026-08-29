#!/usr/bin/env python3
"""Replay layout geometry against every page in a reference directory.

The single-page layout guard cannot prove that a multi-page layout did not
silently omit a page.  This gate checks page-number coverage first, then
replays each page's source bboxes and placement coordinates independently.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json
from layout_guard import _as_float_list, _check_box_match, _load_deck, _required_box_fields


def _pages(value: str | None) -> set[int] | None:
    if not value:
        return None
    selected: set[int] = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            raise ValueError("empty page selector")
        if "-" in token:
            lo, hi = (int(part.strip()) for part in token.split("-", 1))
            if lo > hi:
                raise ValueError("page range is reversed")
            selected.update(range(lo, hi + 1))
        else:
            selected.add(int(token))
    if not selected or min(selected) < 1:
        raise ValueError("pages must be positive")
    return selected


def _decode(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            size = image.size
            image.convert("RGB").load()
            return size
    except Exception:
        return None


def validate(reference_dir: Path, layout_path: Path, expected_pages: int, *, selected: set[int] | None, strict: bool, expected_ratio: float) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if expected_pages < 1:
        errors.append({"severity": "blocker", "code": "expected_pages_invalid", "expected_pages": expected_pages})
    if not math.isfinite(expected_ratio) or expected_ratio <= 0:
        errors.append({"severity": "blocker", "code": "expected_ratio_invalid", "expected_ratio": expected_ratio})
    reference_dir = reference_dir.resolve()
    layout_path = layout_path.resolve()
    try:
        deck = _load_deck(layout_path)
    except Exception as exc:
        return {"schema": "ai-ppt-plus/multipage-layout-validation/v1", "valid": False, "status": "invalid", "reference_dir": str(reference_dir), "layout": str(layout_path), "issues": [{"severity": "blocker", "code": "layout_unreadable", "message": f"{type(exc).__name__}: {exc}"}], "warnings": [], "human_visual_review_required": True}

    raw_slides = deck.get("slides") if isinstance(deck.get("slides"), list) else []
    slides: dict[int, dict[str, Any]] = {}
    for index, slide in enumerate(raw_slides, 1):
        if not isinstance(slide, dict):
            errors.append({"severity": "blocker", "code": "layout_slide_invalid", "slide_no": index})
            continue
        try:
            number = int(slide.get("slide_no", index))
        except (TypeError, ValueError):
            errors.append({"severity": "blocker", "code": "layout_slide_number_invalid", "index": index})
            continue
        if number in slides:
            errors.append({"severity": "blocker", "code": "layout_slide_number_duplicate", "slide_no": number})
        slides[number] = slide

    audit_numbers = sorted(selected) if selected is not None else list(range(1, expected_pages + 1))
    if selected is not None and (min(selected) < 1 or max(selected) > expected_pages):
        errors.append({"severity": "blocker", "code": "selected_page_out_of_range", "selected": sorted(selected), "expected_pages": expected_pages})
    if selected is None:
        observed = sorted(slides)
        if observed != list(range(1, expected_pages + 1)):
            errors.append({"severity": "blocker", "code": "layout_page_coverage_mismatch", "expected": list(range(1, expected_pages + 1)), "observed": observed})

    units = deck.get("units", "fraction")
    if units not in {"fraction", "px"}:
        errors.append({"severity": "blocker", "code": "layout_units_invalid", "observed": units})
    ref_width = float(deck.get("ref_width") or 0)
    ref_height = float(deck.get("ref_height") or 0)
    if ref_width <= 0 or ref_height <= 0:
        warnings.append({"severity": "major", "code": "layout_reference_size_missing"})

    page_results = []
    for slide_no in audit_numbers:
        page_errors: list[dict[str, Any]] = []
        page_warnings: list[dict[str, Any]] = []
        reference = reference_dir / f"slide-{slide_no}.png"
        size = _decode(reference) if reference.is_file() else None
        if not reference.is_file():
            page_errors.append({"severity": "blocker", "code": "reference_page_missing", "slide_no": slide_no, "path": str(reference)})
        elif size is None:
            page_errors.append({"severity": "blocker", "code": "reference_page_decode_failed", "slide_no": slide_no, "path": str(reference)})
        else:
            ratio = size[0] / size[1] if size[1] else 0
            if abs(ratio - expected_ratio) > 0.02:
                page_errors.append({"severity": "blocker", "code": "reference_ratio_unexpected", "slide_no": slide_no, "ratio": ratio})
        slide = slides.get(slide_no)
        if slide is None:
            page_errors.append({"severity": "blocker", "code": "layout_page_missing", "slide_no": slide_no})
            page_results.append({"slide_no": slide_no, "reference": str(reference), "size": list(size) if size else None, "errors": page_errors, "warnings": page_warnings})
            errors.extend(page_errors)
            continue
        page_ref_width = float(slide.get("ref_width") or ref_width or (size[0] if size else 0))
        page_ref_height = float(slide.get("ref_height") or ref_height or (size[1] if size else 0))
        if size and page_ref_width > 0 and page_ref_height > 0:
            scale_x, scale_y = size[0] / page_ref_width, size[1] / page_ref_height
            if not math.isclose(scale_x, scale_y, rel_tol=0.005, abs_tol=0.005):
                page_errors.append({"severity": "blocker", "code": "reference_layout_scale_not_uniform", "slide_no": slide_no, "reference_size": list(size), "layout_size": [page_ref_width, page_ref_height]})
        for kind in ("icons", "texts"):
            values = slide.get(kind, [])
            if not isinstance(values, list):
                page_errors.append({"severity": "blocker", "code": "positioned_items_not_array", "slide_no": slide_no, "kind": kind})
                continue
            for index, item in enumerate(values, 1):
                if not isinstance(item, dict):
                    page_errors.append({"severity": "blocker", "code": "positioned_item_invalid", "slide_no": slide_no, "kind": kind, "index": index})
                    continue
                label = str(item.get("object_id") or item.get("name") or item.get("file") or f"{kind}[{index}]")
                bbox = _as_float_list(item.get("source_bbox"), "source_bbox")
                if not _required_box_fields(item):
                    page_errors.append({"severity": "blocker", "code": "placement_box_missing", "slide_no": slide_no, "kind": kind, "object_id": label})
                    continue
                if bbox is None:
                    issue = {"severity": "blocker" if strict else "warning", "code": "source_bbox_missing", "slide_no": slide_no, "kind": kind, "object_id": label}
                    (page_errors if strict else page_warnings).append(issue)
                    continue
                bx, by, bw, bh = bbox
                if bw <= 0 or bh <= 0 or bx < -2 or by < -2 or (page_ref_width and bx + bw > page_ref_width + 2) or (page_ref_height and by + bh > page_ref_height + 2):
                    page_errors.append({"severity": "blocker", "code": "source_bbox_out_of_bounds", "slide_no": slide_no, "kind": kind, "object_id": label, "source_bbox": bbox})
                    continue
                matched, delta = _check_box_match(item, bbox, units, page_ref_width, page_ref_height, 0.0025, 2.0)
                if not matched:
                    page_errors.append({"severity": "blocker", "code": "placement_source_bbox_mismatch", "slide_no": slide_no, "kind": kind, "object_id": label, "max_delta": delta})
        page_results.append({"slide_no": slide_no, "reference": str(reference), "size": list(size) if size else None, "errors": page_errors, "warnings": page_warnings})
        errors.extend(page_errors)
        warnings.extend(page_warnings)

    return {
        "schema": "ai-ppt-plus/multipage-layout-validation/v1",
        "valid": not errors,
        "status": "passed" if not errors else "blocked",
        "reference_dir": str(reference_dir),
        "layout": str(layout_path),
        "expected_pages": expected_pages,
        "selected_pages": sorted(selected) if selected is not None else "all",
        "pages": page_results,
        "issues": errors,
        "warnings": warnings,
        "strict": strict,
        "human_visual_review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_dir")
    parser.add_argument("layout")
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--expected-ratio", type=float, default=16 / 9)
    parser.add_argument("--pages")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        selected = _pages(args.pages)
        result = validate(Path(args.reference_dir), Path(args.layout), args.expected_pages, selected=selected, strict=args.strict, expected_ratio=args.expected_ratio)
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/multipage-layout-validation/v1", "valid": False, "status": "invalid", "issues": [{"severity": "blocker", "code": "runtime_error", "message": f"{type(exc).__name__}: {exc}"}], "warnings": []}
    atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
