#!/usr/bin/env python3
"""Validate one deck-wide design system and its cross-page bindings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json

try:
    import yaml
except ImportError:  # pragma: no cover - reported as a deterministic input error
    yaml = None


REQUIRED = ("schema_version", "revision", "canvas", "grid", "typography", "colors", "spacing", "shapes", "lines", "icons", "images", "charts", "backgrounds", "approval_status")
APPROVALS = {"draft", "approved", "revision-required", "blocked"}


def _contrast(first: str, second: str) -> float | None:
    def channel(value: str) -> float:
        number = int(value, 16) / 255
        return number / 12.92 if number <= 0.04045 else ((number + 0.055) / 1.055) ** 2.4

    try:
        a = first.strip().lstrip("#")
        b = second.strip().lstrip("#")
        if len(a) != 6 or len(b) != 6:
            return None
        la = 0.2126 * channel(a[0:2]) + 0.7152 * channel(a[2:4]) + 0.0722 * channel(a[4:6])
        lb = 0.2126 * channel(b[0:2]) + 0.7152 * channel(b[2:4]) + 0.0722 * channel(b[4:6])
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
    except (TypeError, ValueError):
        return None


def validate(path: Path, *, visual_plan: Path | None = None, slide_manifest: Path | None = None, strict: bool = False) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if yaml is None:
        issues.append({"severity": "blocker", "code": "yaml_runtime_missing"})
        return {"schema": "ai-ppt-plus/design-system-validation/v1", "valid": False, "status": "blocked", "issues": issues, "warnings": warnings}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return {"schema": "ai-ppt-plus/design-system-validation/v1", "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "design_system_unreadable", "message": str(exc)}], "warnings": warnings}
    if not isinstance(data, dict):
        issues.append({"severity": "blocker", "code": "design_system_not_object"})
        data = {}
    for key in REQUIRED:
        if key not in data:
            issues.append({"severity": "blocker", "code": "design_system_field_missing", "field": key})
    revision = data.get("revision")
    if not isinstance(revision, (int, str)) or not str(revision).strip():
        issues.append({"severity": "blocker", "code": "design_system_revision_invalid"})
    canvas = data.get("canvas") if isinstance(data.get("canvas"), dict) else {}
    if canvas.get("ratio") != "16:9":
        issues.append({"severity": "blocker", "code": "design_system_canvas_ratio_invalid", "observed": canvas.get("ratio")})
    try:
        width = float(canvas["width_in"])
        height = float(canvas["height_in"])
        if abs(width / height - 16 / 9) >= 0.01:
            issues.append({"severity": "blocker", "code": "design_system_canvas_dimensions_invalid"})
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        issues.append({"severity": "blocker", "code": "design_system_canvas_dimensions_missing"})
    grid = data.get("grid") if isinstance(data.get("grid"), dict) else {}
    try:
        if int(grid["columns"]) < 1 or float(grid["gutter_in"]) <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        issues.append({"severity": "blocker", "code": "design_system_grid_invalid"})
    typography = data.get("typography") if isinstance(data.get("typography"), dict) else {}
    if not isinstance(typography.get("primary_font"), str) or not typography.get("primary_font").strip():
        issues.append({"severity": "blocker", "code": "design_system_primary_font_missing"})
    sizes = typography.get("sizes_pt") if isinstance(typography.get("sizes_pt"), dict) else {}
    numeric_sizes = {}
    for name, value in sizes.items():
        try:
            numeric_sizes[name] = float(value)
            if numeric_sizes[name] <= 0:
                raise ValueError
        except (TypeError, ValueError):
            issues.append({"severity": "blocker", "code": "design_system_font_size_invalid", "field": name})
    if numeric_sizes and not (numeric_sizes.get("cover", 0) >= numeric_sizes.get("title", 0) >= numeric_sizes.get("body", 0) >= numeric_sizes.get("caption", 0)):
        issues.append({"severity": "blocker", "code": "design_system_type_hierarchy_invalid"})
    colors = data.get("colors") if isinstance(data.get("colors"), dict) else {}
    for name in ("background", "text_primary", "text_secondary", "accent"):
        if not isinstance(colors.get(name), str) or _contrast(colors.get(name), colors.get(name)) is None:
            issues.append({"severity": "blocker", "code": "design_system_color_invalid", "field": name})
    contrast = _contrast(str(colors.get("text_primary", "")), str(colors.get("background", "")))
    if contrast is not None and contrast < 4.5:
        issues.append({"severity": "blocker", "code": "design_system_text_contrast_low", "ratio": round(contrast, 3)})
    if not isinstance(data.get("slide_types", []), list):
        issues.append({"severity": "blocker", "code": "design_system_slide_types_invalid"})
    if not isinstance(data.get("components", []), list):
        issues.append({"severity": "blocker", "code": "design_system_components_invalid"})
    if not isinstance(data.get("exceptions", []), list):
        issues.append({"severity": "blocker", "code": "design_system_exceptions_invalid"})
    if not data.get("slide_types"):
        warnings.append({"code": "design_system_page_families_undeclared"})
    if strict and data.get("approval_status") != "approved":
        issues.append({"severity": "blocker", "code": "design_system_not_approved", "observed": data.get("approval_status")})
    expected_revision = str(revision)
    bindings = []
    for label, candidate in (("visual_plan", visual_plan), ("slide_manifest", slide_manifest)):
        if candidate is None or not candidate.is_file():
            continue
        try:
            bound = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            issues.append({"severity": "blocker", "code": "design_system_binding_unreadable", "artifact": label})
            continue
        if not isinstance(bound, dict):
            continue
        observed = bound.get("design_system_revision")
        if observed is not None and str(observed) != expected_revision:
            issues.append({"severity": "blocker", "code": "design_system_revision_mismatch", "artifact": label, "expected": expected_revision, "observed": observed})
        bindings.append({"artifact": label, "path": str(candidate), "revision": observed})
    return {"schema": "ai-ppt-plus/design-system-validation/v1", "valid": not any(item.get("severity") == "blocker" for item in issues), "status": "passed" if not issues else "blocked", "design_system_path": str(path), "design_system_revision": revision, "bindings": bindings, "issues": issues, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design_system")
    parser.add_argument("--visual-plan")
    parser.add_argument("--slide-manifest")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    result = validate(Path(args.design_system).resolve(), visual_plan=Path(args.visual_plan).resolve() if args.visual_plan else None, slide_manifest=Path(args.slide_manifest).resolve() if args.slide_manifest else None, strict=args.strict)
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
