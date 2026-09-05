#!/usr/bin/env python3
"""Fail closed when 12-case editable candidates are technically valid but visually low-fidelity."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
EDITABLE = REPO / "ai-ppt-editable"
sys.path.insert(0, str(EDITABLE))

from reconstruction.quality_policy import DEFAULT_POLICY, POLICY_VERSION


def finite_score(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in {float("inf"), float("-inf")} else None


def validate(evaluation: dict) -> dict:
    cases = evaluation.get("cases") if isinstance(evaluation.get("cases"), list) else []
    results = []
    for item in cases:
        case_id = str(item.get("case_id") or "")
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        visual = candidate.get("visual") if isinstance(candidate.get("visual"), dict) else {}
        metrics = visual.get("metrics") if isinstance(visual.get("metrics"), dict) else {}
        layout = finite_score(metrics.get("blurred_layout_ssim"))
        global_score = finite_score(metrics.get("pixel_fidelity_score"))
        failures = []
        if candidate.get("technical_status") != "passed":
            failures.append({"code": "technical_gate_not_passed", "observed": candidate.get("technical_status")})
        if visual.get("valid") is not True:
            failures.append({"code": "visual_comparison_invalid"})
        if layout is None:
            failures.append({"code": "layout_similarity_missing"})
        elif layout < DEFAULT_POLICY.layout_similarity:
            failures.append({"code": "layout_similarity_below_policy", "observed": layout, "threshold": DEFAULT_POLICY.layout_similarity})
        if global_score is None:
            failures.append({"code": "pixel_fidelity_missing"})
        elif global_score < DEFAULT_POLICY.global_visual_similarity:
            failures.append({"code": "pixel_fidelity_below_policy", "observed": global_score, "threshold": DEFAULT_POLICY.global_visual_similarity})
        results.append({
            "case_id": case_id,
            "passed": not failures,
            "technical_status": candidate.get("technical_status"),
            "blurred_layout_ssim": layout,
            "pixel_fidelity_score": global_score,
            "failures": failures,
        })
    failed = [item for item in results if not item["passed"]]
    return {
        "schema": "ai-ppt-plus/12-case-visual-fidelity-gate/v1",
        "policy_version": POLICY_VERSION,
        "thresholds": {
            "blurred_layout_ssim": DEFAULT_POLICY.layout_similarity,
            "pixel_fidelity_score": DEFAULT_POLICY.global_visual_similarity,
        },
        "case_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed_count": len(failed),
        "valid": bool(results) and not failed,
        "cases": results,
        "human_visual_review_required": True,
        "release_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-evaluation", default=str(ROOT / "candidate-evaluation.json"))
    parser.add_argument("--report", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    source = Path(args.candidate_evaluation)
    evaluation = json.loads(source.read_text(encoding="utf-8"))
    result = validate(evaluation)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "valid": result["valid"],
        "policy_version": result["policy_version"],
        "passed_count": result["passed_count"],
        "failed_count": result["failed_count"],
        "failed_cases": [item["case_id"] for item in result["cases"] if not item["passed"]],
    }, ensure_ascii=False))
    if args.strict and not result["valid"]:
        raise SystemExit("12-case visual fidelity gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
