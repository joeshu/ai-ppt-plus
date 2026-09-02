#!/usr/bin/env python3
"""Select direct, adjacent, and P0 distillation cases from the matrix."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MATRIX_SCHEMA = "ai-ppt-plus/distillation-case-matrix/v1"
ADJACENT = {
    "routing": {"routing", "package-contract"},
    "native-structure": {"native-structure", "text-visual"},
    "text-visual": {"text-visual", "native-structure"},
    "package-contract": {"package-contract", "routing"},
    "cache-integrity": {"cache-integrity", "package-contract"},
}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != MATRIX_SCHEMA:
        raise ValueError(f"invalid case matrix: {path}")
    if not isinstance(value.get("cases"), list):
        raise ValueError("case matrix cases must be an array")
    return value


def select(matrix: dict[str, Any], *, full: bool, categories: set[str], priorities: set[str]) -> list[dict[str, Any]]:
    cases = [case for case in matrix["cases"] if isinstance(case, dict)]
    if full or (not categories and not priorities):
        return cases
    expanded = set()
    for category in categories:
        expanded.update(ADJACENT.get(category, {category}))
    selected = []
    for case in cases:
        if case.get("priority") in priorities or case.get("responsibility") in expanded:
            selected.append(case)
    # Safety cases are always included in targeted runs.
    selected_ids = {case.get("case_id") for case in selected}
    for case in cases:
        if case.get("priority") == "P0" and case.get("case_id") not in selected_ids:
            selected.append(case)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--full", action="store_true", help="select the complete matrix")
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--priority", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        matrix = load(args.matrix)
        selected = select(
            matrix,
            full=args.full,
            categories=set(args.category),
            priorities=set(args.priority),
        )
    except Exception as exc:
        report = {
            "schema": "ai-ppt-plus/distillation-case-selection/v1",
            "valid": False,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 2

    selected_ids = [case.get("case_id") for case in selected]
    replay_cases = [case for case in selected if case.get("mode") in {"replay", "both"}]
    actual_replay = [
        case.get("case_id") for case in replay_cases
        if case.get("status") == "ready" and not (case.get("replay") or {}).get("static_sentinel")
    ]
    sentinel_replay = [
        case.get("case_id") for case in replay_cases
        if (case.get("replay") or {}).get("static_sentinel") or case.get("status") == "sentinel"
    ]
    planned = [case.get("case_id") for case in selected if case.get("status") == "planned"]
    report = {
        "schema": "ai-ppt-plus/distillation-case-selection/v1",
        "valid": True,
        "status": "passed",
        "selection_mode": "full" if args.full or (not args.category and not args.priority) else "targeted",
        "requested_categories": args.category,
        "requested_priorities": args.priority,
        "selected_case_ids": selected_ids,
        "selected_cases": selected,
        "required_replay_cases": [case.get("case_id") for case in replay_cases],
        "actual_replay_cases": actual_replay,
        "static_sentinel_cases": sentinel_replay,
        "planned_cases": planned,
        "contract_cases": [case.get("case_id") for case in selected if case.get("mode") in {"contract", "both"}],
        "coverage_debt": [
            {"case_id": case.get("case_id"), "kind": "static-sentinel", "message": "regenerate candidate after repair"}
            for case in replay_cases if case.get("case_id") in sentinel_replay
        ] + [
            {"case_id": case.get("case_id"), "kind": "planned", "message": "replay fixture not ready"}
            for case in selected if case.get("status") == "planned"
        ],
        "promotion_blocked_by_replay_debt": bool(replay_cases and not actual_replay),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
