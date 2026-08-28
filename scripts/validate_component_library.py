#!/usr/bin/env python3
"""Validate the reusable component-library contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "ai-ppt-plus/component-library/v1"
LEVELS = {"L0", "L1", "L2", "L3", "L4", "L5"}


def validate(data: dict) -> list[dict]:
    issues = []
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return [{"severity": "blocker", "code": "schema_invalid"}]
    components = data.get("components")
    if not isinstance(components, list) or not components:
        return [{"severity": "blocker", "code": "components_missing"}]
    seen = set()
    for index, component in enumerate(components):
        prefix = f"components[{index}]"
        if not isinstance(component, dict):
            issues.append({"severity": "blocker", "code": "component_not_object", "path": prefix})
            continue
        cid = component.get("component_id")
        if not isinstance(cid, str) or not cid.strip():
            issues.append({"severity": "blocker", "code": "component_id_missing", "path": prefix})
        elif cid in seen:
            issues.append({"severity": "blocker", "code": "component_id_duplicate", "component_id": cid})
        else:
            seen.add(cid)
        if component.get("type") not in {"text", "shape", "group", "table", "chart", "image", "vector"}:
            issues.append({"severity": "blocker", "code": "component_type_invalid", "path": prefix})
        if component.get("editability_level") not in LEVELS:
            issues.append({"severity": "blocker", "code": "editability_level_invalid", "path": prefix})
        if not isinstance(component.get("allowed_layouts"), list) or not component["allowed_layouts"]:
            issues.append({"severity": "blocker", "code": "allowed_layouts_missing", "path": prefix})
        if not isinstance(component.get("defaults", {}), dict):
            issues.append({"severity": "blocker", "code": "defaults_invalid", "path": prefix})
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest")
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    path = Path(args.manifest)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        issues = validate(data)
    except Exception as exc:
        issues = [{"severity": "blocker", "code": "manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"}]
    result = {"schema": "ai-ppt-plus/component-library-validation/v1", "valid": not issues, "manifest": str(path.resolve()), "component_count": len(data.get("components", [])) if isinstance(data, dict) else 0, "issues": issues}
    report = Path(args.report); report.parent.mkdir(parents=True, exist_ok=True); report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
