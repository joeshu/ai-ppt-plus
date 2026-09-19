#!/usr/bin/env python3
"""Bind authored charts to the validated reconstruction representation contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_chart_manifest import validate as validate_chart_manifest


def validate_chart_authoring_contract(layout_path: Path, deck: dict) -> dict:
    authored = []
    for slide_no, slide in enumerate(deck.get("slides") or [], 1):
        for index, chart in enumerate(slide.get("charts") or [], 1):
            if not isinstance(chart, dict):
                continue
            authored.append({"slide_no": slide_no, "chart_id": str(chart.get("object_id") or chart.get("chart_id") or chart.get("name") or f"chart-{index}")})
    result = {"schema": "ai-ppt-plus/chart-authoring-contract/v1", "valid": True, "required": bool(authored), "authored_charts": authored, "issues": []}
    if not authored:
        return result
    manifest_path = layout_path.resolve().parent / "chart-reconstruction.json"
    if not manifest_path.is_file():
        result["valid"] = False
        result["issues"].append({"severity": "blocker", "code": "chart_reconstruction_manifest_missing", "path": str(manifest_path)})
        return result
    manifest_report = validate_chart_manifest(manifest_path)
    result["manifest_validation"] = manifest_report
    if not manifest_report.get("valid"):
        result["issues"].append({"severity": "blocker", "code": "chart_reconstruction_manifest_invalid", "errors": manifest_report.get("errors", [])})
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared = {(int(item.get("slide_no", 0)), str(item.get("chart_id"))) for item in (data.get("charts") or []) if isinstance(item, dict)}
    missing = [item for item in authored if (item["slide_no"], item["chart_id"]) not in declared]
    if missing:
        result["issues"].append({"severity": "blocker", "code": "authored_chart_manifest_coverage_missing", "charts": missing})
    result["valid"] = not result["issues"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    deck = json.loads(args.layout.read_text(encoding="utf-8"))
    report = validate_chart_authoring_contract(args.layout.resolve(), deck)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
