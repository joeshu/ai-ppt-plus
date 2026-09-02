#!/usr/bin/env python3
"""Validate that an unattended distillation candidate is a real improvement.

This is an evidence gate, not a repair engine.  It compares a baseline
evaluation with a candidate evaluation and only returns success when the
candidate demonstrates a red-green transition, an explicit behavioural
change, and no metric or regression degradation.  A case specification can
add object-level checks for reconstruction cases (for example native tables
and editable panels).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "ai-ppt-plus/distillation-improvement/v1"
EVALUATION_SCHEMA = "ai-ppt-plus/distillation-evaluation/v1"
CASE_EVALUATION_SCHEMA = "ai-ppt-plus/pptx-case-evaluation/v1"

LOWER_IS_BETTER = {
    "error_count",
    "failed_gate_count",
    "failure_count",
    "formal_text_in_raster_count",
    "overflow_count",
    "overlap_count",
    "unresolved_assets",
    "whole_slide_picture_count",
    "whole_slide_pictures",
    "forbidden_engine_count",
    "regression_count",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check(checks: list[dict[str, Any]], check_id: str, passed: bool, detail: str) -> None:
    checks.append({"id": check_id, "status": "passed" if passed else "failed", "detail": detail})


def status_of(value: dict[str, Any]) -> str:
    return str(value.get("status") or value.get("conclusion") or "").strip().lower()


def gate_failures(value: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    gates = value.get("gates")
    if isinstance(gates, list):
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            if str(gate.get("status") or "").lower() not in {"passed", "pass", "success"}:
                failures.append(str(gate.get("id") or gate.get("code") or "unknown-gate"))
    for item in value.get("failure_codes") or []:
        if isinstance(item, str) and item not in failures:
            failures.append(item)
    return failures


def candidate_gates_pass(value: dict[str, Any]) -> bool:
    if value.get("valid") is False:
        return False
    gates = value.get("gates")
    if isinstance(gates, list) and gates:
        return all(
            isinstance(gate, dict)
            and str(gate.get("status") or "").lower() in {"passed", "pass", "success"}
            for gate in gates
        )
    return status_of(value) in {"passed", "pass", "success", "accepted", "green"} or value.get("valid") is True


def numeric_metrics(value: dict[str, Any]) -> dict[str, float | int]:
    metrics = value.get("metrics")
    if not isinstance(metrics, dict):
        return {}
    result: dict[str, float | int] = {}
    for key, item in metrics.items():
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            continue
        result[str(key)] = item
    return result


def metric_checks(
    baseline: dict[str, Any], candidate: dict[str, Any], checks: list[dict[str, Any]],
    case_spec: dict[str, Any] | None = None,
) -> None:
    baseline_metrics = baseline.get("metrics")
    candidate_metrics = candidate.get("metrics")
    if baseline_metrics is None and candidate_metrics is None:
        check(checks, "metric-evidence", True, "no numeric metrics were declared")
        return
    if not isinstance(baseline_metrics, dict) or not isinstance(candidate_metrics, dict):
        check(checks, "metric-evidence", False, "both evaluations must provide metrics objects")
        return
    visual_thresholds = ((case_spec or {}).get("quality_thresholds") or {}).get("visual", {})
    threshold_metrics = {
        str(key)[4:]
        for key in visual_thresholds
        if isinstance(key, str) and (key.startswith("min_") or key.startswith("max_"))
    }
    shared = sorted((set(baseline_metrics) & set(candidate_metrics)) - threshold_metrics)
    missing = sorted(set(baseline_metrics) - set(candidate_metrics))
    check(
        checks,
        "metric-completeness",
        not missing,
        "candidate contains all baseline metrics" if not missing else f"missing metrics: {', '.join(missing)}",
    )
    for key in shared:
        before = baseline_metrics[key]
        after = candidate_metrics[key]
        if isinstance(before, bool) or isinstance(after, bool):
            continue
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            continue
        lower_is_better = key in LOWER_IS_BETTER or key.endswith("_errors") or key.endswith("_failures")
        passed = after <= before if lower_is_better else after >= before
        direction = "not higher" if lower_is_better else "not lower"
        check(checks, f"metric:{key}", passed, f"baseline={before}, candidate={after}; candidate is {direction}")
    for key, threshold in visual_thresholds.items():
        if not isinstance(key, str) or not isinstance(threshold, (int, float)):
            continue
        metric = key[4:] if key.startswith(("min_", "max_")) else key
        observed = candidate_metrics.get(metric)
        if key.startswith("min_"):
            passed = isinstance(observed, (int, float)) and observed >= threshold
            detail = f"candidate={observed}, minimum={threshold}"
        elif key.startswith("max_"):
            passed = isinstance(observed, (int, float)) and observed <= threshold
            detail = f"candidate={observed}, maximum={threshold}"
        else:
            continue
        check(checks, f"case-metric:{metric}", passed, detail)


def _path_label(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "$"


def expected_matches(expected: Any, observed: Any, path: tuple[str, ...] = ()) -> tuple[bool, str]:
    """Compare case expectations with tolerant semantics for required assets.

    Most scalar values are exact.  ``native_table_shapes`` is a required
    subset because additional native tables are not a regression.  Picture
    budgets are upper bounds because fewer raster objects are better.
    """
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            return False, f"{_path_label(path)} expected an object"
        for key, wanted in expected.items():
            if key not in observed:
                return False, f"missing {_path_label(path + (str(key),))}"
            passed, detail = expected_matches(wanted, observed[key], path + (str(key),))
            if not passed:
                return False, detail
        return True, f"matched {_path_label(path)}"
    if isinstance(expected, list):
        if not isinstance(observed, list):
            return False, f"{_path_label(path)} expected a list"
        if path[-1:] == ("native_table_shapes",):
            missing = [item for item in expected if item not in observed]
            return (not missing, f"missing native table shapes: {missing}" if missing else "required native table shapes present")
        if path[-1:] == ("merged_cells",):
            normalized_expected = sorted(json.dumps(item, sort_keys=True) for item in expected)
            normalized_observed = sorted(json.dumps(item, sort_keys=True) for item in observed)
            return (
                normalized_expected == normalized_observed,
                "merged-cell topology matches" if normalized_expected == normalized_observed else "merged-cell topology differs",
            )
        return (expected == observed, f"{_path_label(path)} list matches" if expected == observed else f"{_path_label(path)} list differs")
    if path[-1:] in {("permitted_full_slide_pictures",), ("whole_slide_pictures",)} and isinstance(expected, (int, float)):
        passed = isinstance(observed, (int, float)) and observed <= expected
        return passed, f"{_path_label(path)} observed={observed}, maximum={expected}"
    passed = expected == observed
    return passed, f"{_path_label(path)} observed={observed!r}, expected={expected!r}"


def regressions_pass(candidate: dict[str, Any], external: list[dict[str, Any]]) -> tuple[bool, str]:
    reports = list(external)
    declared = candidate.get("regressions")
    if isinstance(declared, list):
        reports.extend(item for item in declared if isinstance(item, dict))
    if not reports:
        # A complete candidate gate list is itself the P0 regression evidence.
        gates = candidate.get("gates")
        if isinstance(gates, list) and gates:
            return candidate_gates_pass(candidate), "candidate gate suite is the regression evidence"
        return False, "no regression evidence was supplied"
    failures: list[str] = []
    for report in reports:
        passed = report.get("valid") is True or status_of(report) in {"passed", "pass", "success", "accepted", "green"}
        if not passed:
            failures.append(str(report.get("case_id") or report.get("id") or "unnamed-regression"))
    return not failures, "all regression reports passed" if not failures else f"failed regressions: {', '.join(failures)}"


def validate(
    baseline: dict[str, Any], candidate: dict[str, Any], *, mode: str,
    case_spec: dict[str, Any] | None, external_regressions: list[dict[str, Any]],
    expected_repair_fingerprint: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    if baseline.get("schema") not in {EVALUATION_SCHEMA, CASE_EVALUATION_SCHEMA, None}:
        check(checks, "baseline-schema", False, f"unexpected baseline schema: {baseline.get('schema')!r}")
        reasons.append("baseline schema is invalid")
    else:
        check(checks, "baseline-schema", True, "baseline schema accepted")
    if candidate.get("schema") not in {EVALUATION_SCHEMA, CASE_EVALUATION_SCHEMA, None}:
        check(checks, "candidate-schema", False, f"unexpected candidate schema: {candidate.get('schema')!r}")
        reasons.append("candidate schema is invalid")
    else:
        check(checks, "candidate-schema", True, "candidate schema accepted")

    baseline_case = baseline.get("case_id")
    candidate_case = candidate.get("case_id")
    same_case = bool(baseline_case and candidate_case and baseline_case == candidate_case)
    check(checks, "same-case", same_case, f"baseline={baseline_case!r}, candidate={candidate_case!r}")
    if not same_case:
        reasons.append("baseline and candidate do not identify the same evaluation")
    baseline_source = baseline.get("source_sha256")
    candidate_source = candidate.get("source_sha256")
    source_ok = not baseline_source or not candidate_source or baseline_source == candidate_source
    check(checks, "same-source", source_ok, "source fingerprints match or were not declared")
    if not source_ok:
        reasons.append("baseline and candidate source fingerprints differ")

    baseline_failed = status_of(baseline) in {"failed", "failure", "blocked", "red"} and bool(gate_failures(baseline) or baseline.get("failure_codes") or baseline.get("valid") is False)
    check(checks, "red-baseline", baseline_failed, "baseline contains a reproducible failure" if baseline_failed else "baseline is not a failed evaluation")
    if not baseline_failed:
        reasons.append("the baseline was not proven red")

    candidate_passed = candidate_gates_pass(candidate)
    check(checks, "green-candidate", candidate_passed, "candidate gates passed" if candidate_passed else "candidate gates did not pass")
    if not candidate_passed:
        reasons.append("the candidate was not proven green")

    changed_files = candidate.get("changed_files")
    behavior_changed = candidate.get("behavioral_change") is True
    baseline_deck = baseline.get("deck") if isinstance(baseline.get("deck"), dict) else {}
    candidate_deck = candidate.get("deck") if isinstance(candidate.get("deck"), dict) else {}
    deck_changed = bool(
        baseline_deck.get("sha256")
        and candidate_deck.get("sha256")
        and baseline_deck.get("sha256") != candidate_deck.get("sha256")
    )
    changed = behavior_changed and (
        (isinstance(changed_files, list) and bool(changed_files)) or deck_changed
    )
    check(
        checks,
        "behavioral-change",
        changed,
        "candidate declares a non-empty implementation/deck change" if changed else "candidate lacks explicit behavioural-change evidence",
    )
    if not changed:
        reasons.append("no explicit behavioural change was proven")

    metric_checks(baseline, candidate, checks, case_spec)

    if mode == "replay" or (mode == "auto" and case_spec is not None):
        expected = (case_spec or {}).get("expected") if isinstance(case_spec, dict) else None
        observed = candidate.get("observed")
        if observed is None and isinstance(candidate.get("replay"), dict):
            observed = candidate["replay"].get("observed")
        replay_ok = isinstance(expected, dict) and isinstance(observed, dict)
        replay_detail = "replay evidence is present" if replay_ok else "case expected/observed evidence is incomplete"
        if replay_ok:
            replay_ok, replay_detail = expected_matches(expected, observed)
        check(checks, "case-replay", replay_ok, replay_detail)
        if not replay_ok:
            reasons.append("case replay did not satisfy the expected editable structure")
        if expected_repair_fingerprint:
            observed_fingerprint = candidate.get("repair_fingerprint")
            fingerprint_ok = observed_fingerprint == expected_repair_fingerprint
            check(
                checks,
                "repair-fingerprint",
                fingerprint_ok,
                "case candidate is bound to the current repair diff" if fingerprint_ok else "case candidate is not bound to the current repair diff",
            )
            if not fingerprint_ok:
                reasons.append("case replay was not generated from the candidate repair")

    regression_ok, regression_detail = regressions_pass(candidate, external_regressions)
    check(checks, "regression-evidence", regression_ok, regression_detail)
    if not regression_ok:
        reasons.append("regression evidence is missing or failing")

    hard_failures = [item for item in checks if item["status"] == "failed"]
    valid = not hard_failures
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "mode": mode,
        "case_id": candidate_case,
        "valid": valid,
        "promotion": "improved" if valid else "no-improvement",
        "checks": checks,
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--case-spec")
    parser.add_argument("--regression", action="append", default=[])
    parser.add_argument("--mode", choices=("auto", "gates", "replay"), default="auto")
    parser.add_argument("--repair-fingerprint")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        baseline = load_json(Path(args.baseline).resolve())
        candidate = load_json(Path(args.candidate).resolve())
        if not isinstance(baseline, dict) or not isinstance(candidate, dict):
            raise ValueError("baseline and candidate must be JSON objects")
        case_spec = None
        if args.case_spec:
            loaded_spec = load_json(Path(args.case_spec).resolve())
            if not isinstance(loaded_spec, dict):
                raise ValueError("case specification must be a JSON object")
            case_spec = loaded_spec
        external = []
        for path_text in args.regression:
            loaded_report = load_json(Path(path_text).resolve())
            if not isinstance(loaded_report, dict):
                raise ValueError(f"regression report must be an object: {path_text}")
            external.append(loaded_report)
        mode = args.mode
        if mode == "auto":
            mode = "replay" if case_spec is not None else "gates"
        result = validate(
            baseline,
            candidate,
            mode=mode,
            case_spec=case_spec,
            external_regressions=external,
            expected_repair_fingerprint=args.repair_fingerprint,
        )
        write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["valid"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": SCHEMA,
            "generated_at": utc_now(),
            "valid": False,
            "promotion": "blocked",
            "reasons": [f"{type(exc).__name__}: {exc}"],
        }
        write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
