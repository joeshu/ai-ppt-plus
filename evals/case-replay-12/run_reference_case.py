#!/usr/bin/env python3
"""Run one replay case through a reference-derived native layout and full technical/visual audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import run_replay_suite as legacy
from reference_layouts import build_reference_layout

ROOT = Path(__file__).resolve().parent
_ORIGINAL = legacy.build_layout


def _apply_reference_rich_text(table):
    object_id = table.get("object_id")
    rows = table.get("rows") or []
    if object_id == "policy-merged-table" and len(rows) > 1 and rows[1]:
        rows[1][0] = {
            "runs": [
                {"text": "新增装机\n", "bold": True, "size": 8.2, "color": "#0A2B5E"},
                {"text": "（新装竣工）", "bold": True, "size": 7.3, "color": "#0A2B5E"},
            ]
        }
    if object_id == "monthly-subsidy-table" and rows:
        rows[-1][0] = {
            "runs": [
                {"text": "本月预计补贴", "bold": True, "size": 8.2, "color": "#E60012"},
                {"text": "（元）", "bold": True, "size": 7.2, "color": "#E60012"},
            ]
        }


def normalize_writer_contract(deck):
    """Normalize reference-fixture shorthand into the current strict writer contract."""
    for slide in deck.get("slides", []) or []:
        for item in slide.get("texts", []) or []:
            if item.get("valign") == "mid":
                item["valign"] = "middle"
        for table in slide.get("tables", []) or []:
            styles = table.get("cell_styles") if isinstance(table.get("cell_styles"), dict) else {}
            for style in styles.values():
                if not isinstance(style, dict):
                    continue
                if style.get("align") == "center":
                    style["align"] = 2  # PP_ALIGN.CENTER, JSON-safe
                if style.get("valign") == "mid":
                    style["valign"] = "middle"
            _apply_reference_rich_text(table)
    return deck


def reference_first(case, run_dir, optimized):
    resolved = build_reference_layout(case, run_dir, optimized, legacy)
    if resolved is not None:
        return normalize_writer_contract(resolved)
    return _ORIGINAL(case, run_dir, optimized)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--suite", default=str(ROOT / "case-suite.json"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--strict-technical", action="store_true")
    args = parser.parse_args()
    suite_path = Path(args.suite)
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    case = next((item for item in suite.get("cases", []) if item.get("case_id") == args.case_id), None)
    if case is None:
        raise SystemExit(f"unknown case: {args.case_id}")
    if build_reference_layout(case, Path(args.output_dir), True, legacy) is None:
        raise SystemExit(f"no reference-derived builder registered for {args.case_id}")

    legacy.build_layout = reference_first
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    reference = ROOT / "visual" / f"{args.case_id}-reference.png"
    result = legacy.native_evaluate(case, output_dir, reference, optimized=True)
    report = {
        "schema": "ai-ppt-plus/reference-case-replay/v1",
        "case_id": args.case_id,
        "reference_builder": True,
        "result": result,
        "visual_metrics": (result.get("visual") or {}).get("metrics") or {},
        "technical_status": result.get("technical_status"),
        "valid": result.get("technical_status") == "passed",
        "human_visual_review_required": True,
        "release_eligible": False,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"case_id": args.case_id, "technical_status": result.get("technical_status"), "visual_metrics": report["visual_metrics"]}, ensure_ascii=False))
    if args.strict_technical and result.get("technical_status") != "passed":
        raise SystemExit("reference case technical gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
