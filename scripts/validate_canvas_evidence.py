#!/usr/bin/env python3
"""Validate reference/render canvas dimensions without silent rescaling.

Visual comparison may normalize same-ratio images for diagnostics.  This gate
keeps that convenience separate from the strict reconstruction contract: a
strict run must prove that every reference and rendered page uses the same
pixel canvas, or carry an explicit image-service degradation record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/canvas-evidence/v1"
DEGRADATION_SCHEMA = "ai-ppt-plus/canvas-degradation/v1"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def raster_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - environment contract owns this
        raise ValueError(f"Pillow is required for canvas evidence: {exc}") from exc
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
    except Exception as exc:
        raise ValueError(f"{path}: raster decode failed: {type(exc).__name__}: {exc}") from exc
    if not width or not height:
        raise ValueError(f"{path}: raster canvas is empty")
    return int(width), int(height)


def page_number(path: Path) -> int:
    try:
        return int(path.stem.rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return 10**9


def page_files(value: str | None, expected_pages: int) -> dict[int, Path]:
    if not value:
        return {}
    path = Path(value).resolve()
    if path.is_file():
        return {1: path}
    if not path.is_dir():
        return {}
    files = {page_number(item): item for item in path.glob("slide-*.png")}
    return {number: item for number, item in files.items() if 1 <= number <= expected_pages}


def positive_pair(value: Any) -> tuple[int, int] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            width, height = int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
        if width > 0 and height > 0:
            return width, height
    return None


def load_degradation(path: Path, issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append({"severity": "blocker", "code": "canvas_degradation_evidence_missing", "path": str(path)})
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append({"severity": "blocker", "code": "canvas_degradation_evidence_unreadable", "message": str(exc)})
        return None
    if not isinstance(data, dict):
        issues.append({"severity": "blocker", "code": "canvas_degradation_evidence_not_object"})
        return None
    if data.get("schema") != DEGRADATION_SCHEMA:
        issues.append({"severity": "blocker", "code": "canvas_degradation_schema_invalid", "observed": data.get("schema")})
    for field in ("service", "reason", "recorded_at"):
        if not isinstance(data.get(field), str) or not data.get(field, "").strip():
            issues.append({"severity": "blocker", "code": "canvas_degradation_field_missing", "field": field})
    if positive_pair(data.get("requested_canvas")) is None:
        issues.append({"severity": "blocker", "code": "canvas_degradation_requested_canvas_invalid"})
    observed = data.get("observed_canvas")
    observed_pair = positive_pair(observed)
    if observed_pair is None and isinstance(observed, dict):
        observed_pair = positive_pair(observed.get("rendered")) or positive_pair(observed.get("source"))
    if observed_pair is None:
        issues.append({"severity": "blocker", "code": "canvas_degradation_observed_canvas_invalid"})
    if data.get("fallback") not in {"native-service-resolution", "resampled-by-service", "provider-limit", "other"}:
        issues.append({"severity": "blocker", "code": "canvas_degradation_fallback_invalid", "observed": data.get("fallback")})
    return data


def validate(
    reference: str | None,
    render_dir: Path,
    expected_pages: int,
    *,
    strict: bool,
    allow_degradation: bool,
    degradation_path: Path | None,
    expected_canvas: tuple[int, int] | None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    references = page_files(reference, expected_pages)
    rendered = page_files(str(render_dir), expected_pages)
    if reference and not references:
        issues.append({"severity": "blocker", "code": "reference_canvas_missing", "path": str(Path(reference).resolve())})
    if not render_dir.is_dir():
        issues.append({"severity": "blocker", "code": "render_canvas_missing", "path": str(render_dir)})

    expected_numbers = set(range(1, expected_pages + 1))
    if references and set(references) != expected_numbers:
        issues.append({"severity": "blocker", "code": "reference_canvas_page_set_mismatch", "expected": sorted(expected_numbers), "observed": sorted(references)})
    if set(rendered) != expected_numbers:
        issues.append({"severity": "blocker", "code": "render_canvas_page_set_mismatch", "expected": sorted(expected_numbers), "observed": sorted(rendered)})

    sizes: dict[str, dict[str, list[int]]] = {"reference": {}, "rendered": {}}
    failures: list[dict[str, Any]] = []
    for label, files in (("reference", references), ("rendered", rendered)):
        for slide, path in sorted(files.items()):
            try:
                size = raster_size(path)
            except ValueError as exc:
                issues.append({"severity": "blocker", "code": "canvas_raster_invalid", "kind": label, "slide": slide, "message": str(exc)})
                continue
            sizes[label][str(slide)] = [size[0], size[1]]
            if expected_canvas and size != expected_canvas:
                failures.append({"kind": label, "slide": slide, "expected": list(expected_canvas), "observed": list(size), "path": str(path)})

    if references:
        unique_reference_sizes = {tuple(value) for value in sizes["reference"].values()}
        if len(unique_reference_sizes) > 1:
            failures.append({"kind": "reference", "code": "reference_canvas_inconsistent", "observed": sorted([list(item) for item in unique_reference_sizes])})
        if expected_canvas is None and len(unique_reference_sizes) == 1:
            expected_canvas = next(iter(unique_reference_sizes))
    if expected_canvas:
        for label, page_sizes in sizes.items():
            for slide, observed in page_sizes.items():
                if tuple(observed) != tuple(expected_canvas):
                    failures.append({"kind": label, "slide": int(slide), "expected": list(expected_canvas), "observed": observed})
    elif strict:
        issues.append({"severity": "blocker", "code": "exact_canvas_target_missing"})

    degradation = None
    if failures:
        if strict and not allow_degradation:
            issues.extend({"severity": "blocker", "code": "canvas_exact_mismatch", **failure} for failure in failures)
        elif allow_degradation:
            if degradation_path is None:
                issues.append({"severity": "blocker", "code": "canvas_degradation_path_missing"})
            else:
                before = len(issues)
                degradation = load_degradation(degradation_path, issues)
                if degradation is not None and len(issues) == before:
                    warnings.extend({"severity": "warning", "code": "canvas_exact_mismatch_recorded", **failure} for failure in failures)
        else:
            warnings.extend({"severity": "warning", "code": "canvas_not_exact", **failure} for failure in failures)

    status = "blocked" if issues else "degraded" if failures else "passed"
    exact = bool(status == "passed" and expected_canvas and not failures)
    result = {
        "schema": SCHEMA,
        "valid": not issues,
        "status": status,
        "strict": strict,
        "exact_canvas": exact,
        "release_eligible": exact,
        "expected_pages": expected_pages,
        "canvas": {
            "expected": list(expected_canvas) if expected_canvas else None,
            "reference": sizes["reference"],
            "rendered": sizes["rendered"],
        },
        "mismatches": failures,
        "degradation": {
            "accepted": bool(degradation and not issues),
            "path": str(degradation_path.resolve()) if degradation_path else None,
            "service": degradation.get("service") if degradation else None,
            "reason": degradation.get("reason") if degradation else None,
        },
        "issues": issues,
        "warnings": warnings,
        "human_visual_review_required": True,
        "limitation": "exact pixel canvas is a prerequisite for strict visual comparison; it does not prove visual or semantic fidelity",
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", help="one reference image or a directory of slide-N.png files")
    parser.add_argument("--render-dir", required=True)
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--expected-width", type=int)
    parser.add_argument("--expected-height", type=int)
    parser.add_argument("--strict", action="store_true", help="block any canvas mismatch")
    parser.add_argument("--allow-degradation", action="store_true", help="accept only with an explicit image-service degradation record")
    parser.add_argument("--degradation-evidence")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    if args.expected_pages < 1:
        result = {"schema": SCHEMA, "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "expected_pages_invalid"}]}
        atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if (args.expected_width is None) != (args.expected_height is None) or (args.expected_width is not None and (args.expected_width < 1 or args.expected_height < 1)):
        result = {"schema": SCHEMA, "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "expected_canvas_invalid"}]}
        atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2
    result = validate(
        args.reference,
        Path(args.render_dir).resolve(),
        args.expected_pages,
        strict=args.strict,
        allow_degradation=args.allow_degradation,
        degradation_path=Path(args.degradation_evidence).resolve() if args.degradation_evidence else None,
        expected_canvas=(args.expected_width, args.expected_height) if args.expected_width is not None else None,
    )
    atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
