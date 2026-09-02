#!/usr/bin/env python3
"""Validate the bounded distillation case matrix and report coverage debt.

The matrix intentionally distinguishes contract tests from actual case replay.
This prevents a green unit-test suite from being mistaken for proof that a
newly distilled PPTX remains editable and visually faithful.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "assets" / "schemas" / "distillation-case-matrix.schema.json"
MATRIX_SCHEMA = "ai-ppt-plus/distillation-case-matrix/v1"
PRIORITIES = {"P0", "P1", "P2"}
MODES = {"contract", "replay", "both"}
STATUSES = {"ready", "planned", "sentinel"}
RESPONSIBILITIES = {
    "routing",
    "native-structure",
    "text-visual",
    "package-contract",
    "cache-integrity",
}
REPLAY_FIELDS = ("spec", "source_deck", "candidate_deck", "reference_image")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_path(value: str) -> Path:
    candidate = Path(value.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        return candidate
    return ROOT / candidate


def validate_matrix(matrix_path: Path, *, strict: bool = False, require_actual_replay: bool = False) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        matrix = load_json(matrix_path)
    except Exception as exc:  # pragma: no cover - exercised through CLI failure path
        return {
            "schema": "ai-ppt-plus/distillation-case-matrix-validation/v1",
            "valid": False,
            "status": "failed",
            "matrix_file": str(matrix_path),
            "errors": [{"code": "read_error", "message": f"{type(exc).__name__}: {exc}"}],
            "warnings": [],
        }

    try:
        from schema_contract import validate as schema_validate

        schema = load_json(SCHEMA_FILE)
        errors.extend(
            {"code": "schema", **issue}
            for issue in schema_validate(matrix, schema)
        )
    except Exception as exc:  # pragma: no cover - protects standalone diagnostics
        errors.append({"code": "schema_loader", "message": f"{type(exc).__name__}: {exc}"})

    if not isinstance(matrix, dict):
        errors.append({"code": "matrix_type", "message": "matrix must be an object"})
        return {
            "schema": "ai-ppt-plus/distillation-case-matrix-validation/v1",
            "valid": False,
            "status": "failed",
            "matrix_file": str(matrix_path),
            "errors": errors,
            "warnings": warnings,
        }

    if matrix.get("schema") != MATRIX_SCHEMA:
        errors.append({"code": "schema_id", "message": f"expected {MATRIX_SCHEMA!r}"})
    policy = matrix.get("policy")
    if not isinstance(policy, dict):
        errors.append({"code": "policy_type", "message": "policy must be an object"})
        policy = {}
    cases = matrix.get("cases")
    if not isinstance(cases, list):
        errors.append({"code": "cases_type", "message": "cases must be an array"})
        cases = []

    required_evidence = policy.get("required_evidence")
    if not isinstance(required_evidence, list) or not required_evidence:
        errors.append({"code": "required_evidence", "message": "policy.required_evidence must be non-empty"})
    if policy.get("static_sentinel_never_promotes") is not True:
        errors.append({"code": "sentinel_policy", "message": "static sentinels must never promote"})
    if policy.get("coverage_debt_is_reported") is not True:
        errors.append({"code": "coverage_debt_policy", "message": "coverage debt must be reported"})

    seen: set[str] = set()
    counts = {priority: 0 for priority in sorted(PRIORITIES)}
    status_counts = {status: 0 for status in sorted(STATUSES)}
    mode_counts = {mode: 0 for mode in sorted(MODES)}
    replay_ready: list[str] = []
    actual_replay_ready: list[str] = []
    contract_cases: list[str] = []
    coverage_debt: list[dict[str, Any]] = []
    selected_filter = set()

    for index, case in enumerate(cases):
        prefix = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append({"code": "case_type", "path": prefix, "message": "case must be an object"})
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append({"code": "case_id", "path": prefix, "message": "case_id must be non-empty"})
            continue
        if case_id in seen:
            errors.append({"code": "duplicate_case_id", "path": prefix, "message": case_id})
        seen.add(case_id)

        priority = case.get("priority")
        responsibility = case.get("responsibility")
        mode = case.get("mode")
        status = case.get("status")
        if priority not in PRIORITIES:
            errors.append({"code": "priority", "path": prefix, "message": f"invalid priority: {priority!r}"})
        else:
            counts[priority] += 1
        if responsibility not in RESPONSIBILITIES:
            errors.append({"code": "responsibility", "path": prefix, "message": f"invalid responsibility: {responsibility!r}"})
        if mode not in MODES:
            errors.append({"code": "mode", "path": prefix, "message": f"invalid mode: {mode!r}"})
        else:
            mode_counts[mode] += 1
        if status not in STATUSES:
            errors.append({"code": "status", "path": prefix, "message": f"invalid status: {status!r}"})
        else:
            status_counts[status] += 1

        tests = case.get("contract_tests")
        if not isinstance(tests, list) or not tests:
            errors.append({"code": "contract_tests", "path": prefix, "message": "at least one contract test is required"})
        else:
            contract_cases.append(case_id)
            for test_path in tests:
                if not isinstance(test_path, str) or not test_path:
                    errors.append({"code": "contract_test_path", "path": prefix, "message": "test path must be a string"})
                elif not repo_path(test_path).is_file():
                    errors.append({"code": "missing_contract_test", "path": prefix, "message": test_path})

        checks = case.get("required_checks")
        if not isinstance(checks, list) or not checks:
            errors.append({"code": "required_checks", "path": prefix, "message": "required_checks must be non-empty"})

        replay_required = case.get("replay_required") is True
        replay = case.get("replay")
        if mode in {"replay", "both"}:
            if not replay_required:
                errors.append({"code": "replay_required", "path": prefix, "message": "replay mode requires replay_required=true"})
            if not isinstance(replay, dict):
                errors.append({"code": "replay_spec", "path": prefix, "message": "replay definition is required"})
                replay = {}
            missing = [field for field in REPLAY_FIELDS if not isinstance(replay.get(field), str) or not replay.get(field)]
            if missing:
                errors.append({"code": "replay_fields", "path": prefix, "message": f"missing: {', '.join(missing)}"})
            else:
                replay_ready.append(case_id)
                for field in REPLAY_FIELDS:
                    value = replay[field]
                    if not repo_path(value).is_file():
                        errors.append({"code": "missing_replay_artifact", "path": prefix, "message": value})
                if replay.get("static_sentinel") is True or status == "sentinel":
                    coverage_debt.append({
                        "case_id": case_id,
                        "kind": "static-sentinel",
                        "message": "fixture replay is runner evidence only; regenerate the candidate after the repair",
                    })
                elif status == "ready":
                    actual_replay_ready.append(case_id)
        elif replay_required:
            coverage_debt.append({
                "case_id": case_id,
                "kind": "missing-replay-mode",
                "message": "replay_required=true but mode is contract-only",
            })

        if status == "planned":
            coverage_debt.append({"case_id": case_id, "kind": "planned", "message": "case has no ready implementation"})
            if priority == "P0":
                errors.append({"code": "p0_not_ready", "path": prefix, "message": "P0 cases cannot remain planned"})
        if priority == "P0" and not isinstance(tests, list):
            errors.append({"code": "p0_contract", "path": prefix, "message": "P0 requires contract tests"})

    for priority in sorted(PRIORITIES):
        if counts[priority] == 0:
            errors.append({"code": "priority_coverage", "message": f"matrix has no {priority} cases"})

    if strict and coverage_debt:
        warnings.extend(coverage_debt)
    if require_actual_replay:
        for debt in coverage_debt:
            if debt.get("kind") in {"static-sentinel", "planned", "missing-replay-mode"}:
                errors.append({"code": "actual_replay_required", **debt})

    summary = {
        "total": len(cases),
        "p0": counts["P0"],
        "p1": counts["P1"],
        "p2": counts["P2"],
        "ready": status_counts["ready"],
        "planned": status_counts["planned"],
        "sentinel": status_counts["sentinel"],
        "contract_cases": len(contract_cases),
        "replay_ready": len(replay_ready),
        "actual_replay_ready": len(actual_replay_ready),
        "coverage_debt": len(coverage_debt),
    }
    valid = not errors
    return {
        "schema": "ai-ppt-plus/distillation-case-matrix-validation/v1",
        "valid": valid,
        "status": "passed" if valid else "failed",
        "matrix_file": str(matrix_path),
        "matrix_schema": matrix.get("schema"),
        "summary": summary,
        "replay_ready_cases": replay_ready,
        "actual_replay_ready_cases": actual_replay_ready,
        "coverage_debt": coverage_debt,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--strict", action="store_true", help="fail on contract/schema errors")
    parser.add_argument("--require-actual-replay", action="store_true", help="also fail on sentinel/planned replay debt")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate_matrix(args.matrix, strict=args.strict, require_actual_replay=args.require_actual_replay)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["valid"] or not args.strict else 2


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
