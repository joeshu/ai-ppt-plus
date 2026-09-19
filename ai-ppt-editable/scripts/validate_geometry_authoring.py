#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

SCHEMA = "ai-ppt-plus/geometry-authoring-audit/v1"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def audit(resolution: dict, pptx: Path) -> dict:
    issues = []
    expected_cubic = sum(
        1 for r in resolution.get("resolutions", [])
        if isinstance(r, dict) and r.get("primitive") == "FREEFORM_BEZIER"
    )
    with zipfile.ZipFile(pptx, "r") as zf:
        slide_xml = b"\n".join(
            zf.read(name)
            for name in zf.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
    cubic_count = slide_xml.count(b"<a:cubicBezTo")
    if expected_cubic and cubic_count < expected_cubic:
        issues.append({
            "severity": "blocker",
            "code": "geometry_cubic_bezier_missing_in_ooxml",
            "detail": f"expected at least {expected_cubic} cubic Bezier path(s), found {cubic_count}",
        })
    return {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "failed",
        "expected_cubic_bezier_count": expected_cubic,
        "actual_cubic_bezier_count": cubic_count,
        "issues": issues,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Validate authored PPTX geometry against primitive-resolution semantics.")
    p.add_argument("geometry_resolution", type=Path)
    p.add_argument("pptx", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        result = audit(load(args.geometry_resolution), args.pptx)
    except Exception as exc:
        result = {
            "schema": SCHEMA, "valid": False, "status": "failed",
            "expected_cubic_bezier_count": 0, "actual_cubic_bezier_count": 0,
            "issues": [{"severity": "blocker", "code": "geometry_authoring_audit_unreadable", "detail": str(exc)}],
        }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.report:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
