#!/usr/bin/env python3
"""Aggregate B1-B4 text-fit evidence across frozen real replay cases.

Batch 5 is deliberately evidence-driven: a case is only PASS when its current
text-fit report and render-feedback report exist and satisfy the frozen
acceptance contract. Missing real inputs/evidence remain NOT_RUN; they are never
silently replaced by synthetic fixtures.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "ai-ppt-plus/text-fit-case-replay/v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(base: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _text_fit_checks(report: dict, acceptance: dict) -> list[dict]:
    slots = [row for row in (report.get("slots") or []) if isinstance(row, dict)]
    checks = []
    overflow = [row.get("object_id") for row in slots if row.get("overflow") is True or row.get("fits") is False]
    checks.append({"name": "text_fit_report_valid", "passed": report.get("valid") is not False})
    checks.append({
        "name": "no_text_overflow",
        "passed": len(overflow) <= int(acceptance.get("overflow_allowed", 0)),
        "details": {"overflow_slots": overflow},
    })
    shrink_order_bad = []
    if acceptance.get("font_shrink_last", True):
        for row in slots:
            repair = row.get("repair") or {}
            if repair.get("font_shrink_last") is False:
                shrink_order_bad.append(row.get("object_id"))
    checks.append({
        "name": "font_shrink_last",
        "passed": not shrink_order_bad,
        "details": {"violations": shrink_order_bad},
    })
    return checks


def _feedback_checks(report: dict, acceptance: dict) -> list[dict]:
    records = [row for row in (report.get("records") or []) if isinstance(row, dict)]
    missing_fresh = []
    if acceptance.get("fresh_render_required_after_repair", True):
        for row in records:
            if row.get("repair_required") and not (row.get("repair") or {}).get("requires_fresh_render"):
                missing_fresh.append(row.get("object_id"))
    return [
        {"name": "render_feedback_valid", "passed": report.get("valid") is True},
        {
            "name": "fresh_render_after_repair",
            "passed": not missing_fresh,
            "details": {"violations": missing_fresh},
        },
    ]


def evaluate(manifest: dict, *, root: Path) -> dict:
    acceptance = manifest.get("acceptance") or {}
    rows = []
    for case in manifest.get("cases") or []:
        case_id = str(case.get("id") or "")
        evidence = case.get("evidence") or {}
        text_fit_path = _resolve(root, evidence.get("text_fit_report"))
        feedback_path = _resolve(root, evidence.get("text_render_feedback"))
        missing = []
        if text_fit_path is None or not text_fit_path.is_file():
            missing.append("text_fit_report")
        if feedback_path is None or not feedback_path.is_file():
            missing.append("text_render_feedback")
        checks = []
        if not missing:
            checks.extend(_text_fit_checks(_load(text_fit_path), acceptance))
            checks.extend(_feedback_checks(_load(feedback_path), acceptance))
        status = "NOT_RUN" if missing else ("PASS" if all(row["passed"] for row in checks) else "FAIL")
        rows.append({
            "id": case_id,
            "name": case.get("name"),
            "source_status": case.get("status"),
            "focus": case.get("focus") or [],
            "status": status,
            "missing_evidence": missing,
            "checks": checks,
        })
    summary = {
        "case_count": len(rows),
        "pass_count": sum(row["status"] == "PASS" for row in rows),
        "fail_count": sum(row["status"] == "FAIL" for row in rows),
        "not_run_count": sum(row["status"] == "NOT_RUN" for row in rows),
    }
    return {
        "schema": SCHEMA,
        "batch": manifest.get("batch"),
        "release_ready": bool(rows) and summary["pass_count"] == len(rows),
        "acceptance": acceptance,
        "summary": summary,
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    root = args.root.resolve() if args.root else manifest_path.parent
    report = evaluate(_load(manifest_path), root=root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report["summary"], "release_ready": report["release_ready"], "report": str(args.report)}, ensure_ascii=False))
    if report["summary"]["fail_count"]:
        return 2
    if args.require_complete and not report["release_ready"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
