#!/usr/bin/env python3
"""Summarize multi-iteration Astra repair convergence for the 12-case suite."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iteration_records(root: Path) -> dict[str, list[dict]]:
    cases: dict[str, list[dict]] = {}
    for path in sorted(root.glob("*/iteration-*/iteration-record.json")):
        record = read_json(path)
        cases.setdefault(record["case_id"], []).append(record)
    for records in cases.values():
        records.sort(key=lambda item: int(item.get("iteration", 0)))
    return cases


def delta(previous: dict, current: dict) -> dict:
    p_score = previous.get("pixel_fidelity_score")
    c_score = current.get("pixel_fidelity_score")
    p_block = int(previous.get("blocking_count", 0))
    c_block = int(current.get("blocking_count", 0))
    visual_delta = None if p_score is None or c_score is None else round(float(c_score) - float(p_score), 6)
    return {
        "from_iteration": previous.get("iteration"),
        "to_iteration": current.get("iteration"),
        "pixel_fidelity_delta": visual_delta,
        "blocking_delta": c_block - p_block,
        "difference_delta": int(current.get("difference_count", 0)) - int(previous.get("difference_count", 0)),
        "repair_action_delta": int(current.get("repair_action_count", 0)) - int(previous.get("repair_action_count", 0)),
        "visual_improved": None if visual_delta is None else visual_delta > 0,
        "blocking_improved": c_block < p_block,
        "regressed": (visual_delta is not None and visual_delta < 0) or c_block > p_block,
    }


def summarize_case(case_id: str, records: list[dict]) -> dict:
    deltas = [delta(records[index - 1], records[index]) for index in range(1, len(records))]
    latest = records[-1]
    regression_count = sum(1 for item in deltas if item["regressed"])
    return {
        "case_id": case_id,
        "iteration_count": len(records),
        "latest_iteration": latest.get("iteration"),
        "latest_status": latest.get("status"),
        "latest_pixel_fidelity_score": latest.get("pixel_fidelity_score"),
        "latest_blocking_count": latest.get("blocking_count"),
        "latest_domain_counts": latest.get("domain_counts"),
        "regression_count": regression_count,
        "converged": latest.get("status") == "gate-ready" and int(latest.get("blocking_count", 0)) == 0,
        "deltas": deltas,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict-no-regression", action="store_true")
    args = parser.parse_args()

    cases = iteration_records(args.root)
    summaries = [summarize_case(case_id, records) for case_id, records in sorted(cases.items())]
    result = {
        "schema": "ai-ppt-plus/astra-convergence-summary/v1",
        "case_count": len(summaries),
        "converged_count": sum(1 for item in summaries if item["converged"]),
        "regressed_case_count": sum(1 for item in summaries if item["regression_count"] > 0),
        "cases": summaries,
    }
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict_no_regression and result["regressed_case_count"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
