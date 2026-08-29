#!/usr/bin/env python3
"""Validate component instances against component and layout libraries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from atomic_output import atomic_write_json


def load(value, base):
    if isinstance(value, dict):
        return value
    path = Path(value)
    if not path.is_absolute():
        candidate = base / path
        path = candidate if candidate.exists() else Path.cwd() / path
    return json.loads(path.read_text(encoding="utf-8"))


def validate(layout, components, layouts):
    definitions = {item.get("component_id"): item for item in components.get("components", []) if isinstance(item, dict)}
    layout_defs = {item.get("layout_id"): item for item in layouts.get("layouts", []) if isinstance(item, dict)}
    issues, counts = [], {}
    theme = layout.get("theme", {}) if isinstance(layout.get("theme", {}), dict) else {}
    for slide_no, slide in enumerate(layout.get("slides", []), 1):
        layout_id = slide.get("layout_id", theme.get("layout_id"))
        layout_name = slide.get("layout_name", theme.get("layout_name", "Blank"))
        allowed_layouts = {layout_id, layout_name}
        if layout_id and layout_id not in layout_defs:
            issues.append({"severity": "blocker", "code": "layout_id_not_found", "slide": slide_no, "layout_id": layout_id})
        if layout_id in layout_defs:
            allowed_layouts.add(layout_defs[layout_id].get("pptx_layout_name"))
        for index, instance in enumerate(slide.get("components", [])):
            cid = instance.get("component_id") if isinstance(instance, dict) else None
            definition = definitions.get(cid)
            if definition is None:
                issues.append({"severity": "blocker", "code": "component_not_found", "slide": slide_no, "index": index, "component_id": cid})
                continue
            counts[cid] = counts.get(cid, 0) + 1
            if not allowed_layouts.intersection(definition.get("allowed_layouts", [])):
                issues.append({"severity": "blocker", "code": "component_layout_mismatch", "slide": slide_no, "component_id": cid})
            primitive = dict(definition.get("template", {})); primitive.update(definition.get("defaults", {})); primitive.update(instance.get("object", {}))
            if definition.get("type") in {"text", "shape", "group", "table", "chart"}:
                for key in ("x", "y", "w", "h"):
                    if key not in primitive:
                        issues.append({"severity": "blocker", "code": "component_bbox_missing", "slide": slide_no, "component_id": cid, "field": key})
                        continue
                    if not 0 <= float(primitive[key]) <= 1:
                        issues.append({"severity": "blocker", "code": "component_bbox_out_of_range", "slide": slide_no, "component_id": cid, "field": key})
    return issues, {"instances": sum(counts.values()), "distinct_components": len(counts), "by_component": dict(sorted(counts.items())), "reused_component_types": sum(1 for count in counts.values() if count > 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument("layout"); ap.add_argument("--components", required=True); ap.add_argument("--layouts", required=True); ap.add_argument("--report", required=True); args = ap.parse_args()
    base = Path(args.layout).resolve().parent
    try:
        layout = json.loads(Path(args.layout).read_text(encoding="utf-8")); components = load(args.components, base); layouts = load(args.layouts, base); issues, usage = validate(layout, components, layouts)
    except Exception as exc:
        issues, usage = [{"severity": "blocker", "code": "validation_error", "message": f"{type(exc).__name__}: {exc}"}], {}
    result = {"schema": "ai-ppt-plus/component-instance-validation/v1", "valid": not issues, "usage": usage, "issues": issues}
    report = Path(args.report); atomic_write_json(report.resolve(), result); print(json.dumps(result, ensure_ascii=False)); return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
