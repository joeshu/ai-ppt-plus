#!/usr/bin/env python3
"""Unify pixel comparison and editable-object comparison evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/dual-comparison/v1"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_json(path: Path, label: str, issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append({"severity": "blocker", "code": f"{label}_missing", "path": str(path)})
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append({"severity": "blocker", "code": f"{label}_unreadable", "message": str(exc)})
        return None
    if not isinstance(data, dict):
        issues.append({"severity": "blocker", "code": f"{label}_not_object"})
        return None
    return data


def manifest_summary(manifest: dict[str, Any] | None) -> dict[str, int]:
    expected = independent = formal_text = 0
    if manifest:
        for slide in manifest.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            objects = slide.get("objects")
            if not isinstance(objects, list):
                continue
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                expected += 1
                role = str(obj.get("role") or "").lower()
                if obj.get("independent") is True or obj.get("required_for_delivery") is True or role in {"icon", "brand_lockup", "semantic-panel", "product-image", "photo", "illustration"}:
                    independent += 1
                if obj.get("object_type") == "editable_text" or obj.get("contains_formal_content") is True:
                    formal_text += 1
    return {"expected_objects": expected, "expected_independent_objects": independent, "expected_formal_text_objects": formal_text}


def build(visual_report_path: Path, output: Path, *, object_report_path: Path | None = None, object_manifest_path: Path | None = None, deck_path: Path | None = None, require_object: bool = False) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    visual = read_json(visual_report_path, "pixel_comparison", issues)
    if visual is not None and visual.get("valid") is not True:
        issues.append({"severity": "blocker", "code": "pixel_comparison_failed", "report_issues": visual.get("issues", [])})
    object_report = read_json(object_report_path, "object_comparison", issues) if object_report_path else None
    manifest = read_json(object_manifest_path, "object_manifest", issues) if object_manifest_path else None
    manifest_counts = manifest_summary(manifest)
    object_evidence: dict[str, Any]
    if object_report is None:
        object_evidence = {"status": "not-run", "valid": False, **manifest_counts}
        if require_object:
            issues.append({"severity": "blocker", "code": "object_comparison_required"})
    else:
        if object_report.get("valid") is not True:
            issues.append({"severity": "blocker", "code": "object_comparison_failed", "report_issues": object_report.get("errors", object_report.get("issues", []))})
        if deck_path and deck_path.is_file() and object_report.get("deck_sha256") and object_report.get("deck_sha256") != digest(deck_path):
            issues.append({"severity": "blocker", "code": "object_comparison_stale_deck", "expected": digest(deck_path), "observed": object_report.get("deck_sha256")})
        if object_manifest_path and object_manifest_path.is_file() and object_report.get("object_manifest_sha256") and object_report.get("object_manifest_sha256") != digest(object_manifest_path):
            issues.append({"severity": "blocker", "code": "object_comparison_stale_manifest", "expected": digest(object_manifest_path), "observed": object_report.get("object_manifest_sha256")})
        expected = manifest_counts["expected_objects"]
        audited = object_report.get("audited_object_count")
        if expected and audited != expected:
            issues.append({"severity": "blocker", "code": "object_comparison_count_mismatch", "expected": expected, "observed": audited})
        object_evidence = {
            "status": "passed" if object_report.get("valid") is True else "blocked",
            "valid": object_report.get("valid") is True,
            **manifest_counts,
            "audited_objects": audited,
            "observed_top_level_shapes": object_report.get("observed_top_level_shape_count"),
            "undeclared_shapes": object_report.get("undeclared_shape_count"),
            "object_manifest_sha256": object_report.get("object_manifest_sha256"),
            "errors": object_report.get("errors", []),
            "warnings": object_report.get("warnings", []),
        }
    pixel_evidence = {
        "status": "passed" if visual and visual.get("valid") is True else "blocked",
        "valid": bool(visual and visual.get("valid") is True),
        "schema": visual.get("schema") if visual else None,
        "compared_pages": len(visual.get("pages", [])) if visual else 0,
        "aggregate": visual.get("aggregate", {}) if visual else {},
        "issues": visual.get("issues", []) if visual else [],
    }
    result = {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "blocked" if issues else "passed" if object_evidence.get("valid") else "partial",
        "comparison_model": {
            "pixel": "reference-image-to-final-render",
            "object": "reference-derived-slide-object-manifest-to-final-pptx",
        },
        "pixel_comparison": pixel_evidence,
        "object_comparison": object_evidence,
        "issues": issues,
        "human_visual_review_required": True,
        "limitation": "pixel similarity does not prove editability; object similarity uses the approved semantic manifest rather than the flattened image object count",
    }
    if deck_path:
        result["deck"] = str(deck_path.resolve())
        result["deck_sha256"] = digest(deck_path) if deck_path.is_file() else None
    if object_manifest_path:
        result["object_manifest"] = str(object_manifest_path.resolve())
    atomic_write_json(output.resolve(), result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-report", required=True)
    parser.add_argument("--object-report")
    parser.add_argument("--object-manifest")
    parser.add_argument("--deck")
    parser.add_argument("--require-object", action="store_true")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        result = build(
            Path(args.visual_report).resolve(),
            Path(args.report).resolve(),
            object_report_path=Path(args.object_report).resolve() if args.object_report else None,
            object_manifest_path=Path(args.object_manifest).resolve() if args.object_manifest else None,
            deck_path=Path(args.deck).resolve() if args.deck else None,
            require_object=args.require_object,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": SCHEMA, "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "dual_comparison_failed", "message": str(exc)}]}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
