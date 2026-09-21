#!/usr/bin/env python3
"""Audit line topology for reference-led editable text.

Reference reconstruction must not silently rely on PowerPoint reflow. A source
line is a visual constraint: implicit wrapping that creates extra lines changes
hierarchy, card density, alignment and neighboring geometry even when the text
technically fits its box.

The layout can opt a slot out with ``allow_reflow: true``. Otherwise explicit
``reference_line_count`` is authoritative; when it is absent, explicit newline
structure is used as the expected topology. The report is designed to pair with
text_fit_deck E3 and the rendered E4 visual gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from text_fit_deck import _slots, _text, audit_layout


def expected_lines(spec: dict, text: str) -> int | None:
    if spec.get("allow_reflow") is True:
        return None
    declared = spec.get("reference_line_count")
    if declared is not None:
        try:
            value = int(declared)
        except (TypeError, ValueError):
            return -1
        return value if value > 0 else -1
    # Only explicit line structure is enforced automatically. A producer that
    # wants one-line preservation should set reference_line_count=1.
    if "\n" in text:
        return max(1, len(text.split("\n")))
    return None


def audit_text_topology(layout: Path) -> dict:
    deck = json.loads(layout.read_text(encoding="utf-8"))
    # Keep topology measurement on the same task-local font as the strict E3
    # fit gate. A host fallback font can invent extra CJK lines and create a
    # false topology failure after the explicit preflight has passed.
    fit = audit_layout(layout, font_file=deck.get("text_fit_font_file"))
    fit_rows = {(row["slide"], row["kind"], row["object_id"]): row for row in fit.get("slots", [])}
    rows, issues = [], []
    for slide_no, kind, object_id, spec, _box in _slots(deck):
        text = _text(spec)
        expected = expected_lines(spec, text)
        if expected is None:
            continue
        row = fit_rows.get((slide_no, kind, object_id))
        observed = None if row is None else row.get("line_count")
        valid = expected > 0 and observed == expected
        record = {"slide": slide_no, "kind": kind, "object_id": object_id, "expected_line_count": expected, "observed_line_count": observed, "valid": valid}
        rows.append(record)
        if not valid:
            issues.append({"severity": "blocker", "code": "reference_line_topology_changed", **record})
    return {
        "schema": "ai-ppt-plus/text-topology/v1",
        "valid": not issues,
        "layout": str(layout.resolve()),
        "checked_slot_count": len(rows),
        "issues": issues,
        "slots": rows,
        "repair_policy": "preserve_reference_lines_by_geometry_before_font_shrink",
        "note": "Rendered E4 visual comparison remains mandatory because font substitution and viewer layout can still change final pixels.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = audit_text_topology(args.layout.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"schema": report["schema"], "valid": report["valid"], "checked_slot_count": report["checked_slot_count"], "issue_count": len(report["issues"])}, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
