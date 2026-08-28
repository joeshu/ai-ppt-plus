#!/usr/bin/env python3
"""Validate the reusable standard-layout contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "ai-ppt-plus/layout-library/v1"


def validate(data: dict) -> list[dict]:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return [{"severity": "blocker", "code": "schema_invalid"}]
    issues, seen = [], set()
    layouts = data.get("layouts")
    if not isinstance(layouts, list) or not layouts:
        return [{"severity": "blocker", "code": "layouts_missing"}]
    for index, item in enumerate(layouts):
        path = f"layouts[{index}]"
        if not isinstance(item, dict):
            issues.append({"severity": "blocker", "code": "layout_not_object", "path": path})
            continue
        layout_id = item.get("layout_id")
        if not isinstance(layout_id, str) or not layout_id.strip():
            issues.append({"severity": "blocker", "code": "layout_id_missing", "path": path})
        elif layout_id in seen:
            issues.append({"severity": "blocker", "code": "layout_id_duplicate", "layout_id": layout_id})
        else:
            seen.add(layout_id)
        if not isinstance(item.get("pptx_layout_name"), str) or not item["pptx_layout_name"].strip():
            issues.append({"severity": "blocker", "code": "pptx_layout_name_missing", "path": path})
        if not isinstance(item.get("page_family"), str) or not item["page_family"].strip():
            issues.append({"severity": "blocker", "code": "page_family_missing", "path": path})
        margins = item.get("safe_margins")
        if not isinstance(margins, list) or len(margins) != 4 or any(not isinstance(value, (int, float)) or not 0 <= value < 0.5 for value in margins):
            issues.append({"severity": "blocker", "code": "safe_margins_invalid", "path": path})
        grid = item.get("grid")
        if not isinstance(grid, dict) or int(grid.get("columns", 0)) <= 0 or not isinstance(grid.get("gutter"), (int, float)) or not 0 <= grid["gutter"] < 0.5:
            issues.append({"severity": "blocker", "code": "grid_invalid", "path": path})
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
        data, issues = {}, [{"severity": "blocker", "code": "manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"}]
    result = {"schema": "ai-ppt-plus/layout-library-validation/v1", "valid": not issues, "manifest": str(path.resolve()), "layout_count": len(data.get("layouts", [])) if isinstance(data, dict) else 0, "issues": issues}
    report = Path(args.report); report.parent.mkdir(parents=True, exist_ok=True); report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
