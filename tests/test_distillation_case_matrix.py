#!/usr/bin/env python3
"""Regression coverage for the distillation case matrix and selector."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "evals" / "distillation-case-matrix.json"
VALIDATOR = ROOT / "scripts" / "validate_distillation_case_matrix.py"
SELECTOR = ROOT / "scripts" / "select_distillation_cases.py"


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    cases = matrix["cases"]
    history_suite = json.loads((ROOT / "evals" / "case-replay-12" / "case-suite.json").read_text(encoding="utf-8"))
    history_ids = {case["case_id"] for case in history_suite["cases"]}
    active_scope = matrix["active_scope"]
    assert len(cases) == 2
    assert {case["priority"] for case in cases} == {"P1"}
    assert matrix["policy"]["required_priorities"] == ["P1"]
    assert set(active_scope["excluded_case_ids"]) == history_ids
    assert {case["case_id"] for case in cases}.isdisjoint(history_ids)
    assert len(active_scope["controlled_limitations"]) == 3
    assert (ROOT / "evals" / "case-replay-12" / "purged-presentation-artifacts.json").is_file()
    assert not list((ROOT / "evals" / "case-replay-12").rglob("*.pptx"))
    assert not list((ROOT / "evals" / "case-replay-12").rglob("*.png"))
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert matrix["policy"]["static_sentinel_never_promotes"] is True

    validation = run(VALIDATOR, "--matrix", str(MATRIX), "--strict")
    assert validation.returncode == 0, validation.stdout + validation.stderr
    report = json.loads(validation.stdout)
    assert report["valid"] is True, report
    assert report["summary"]["total"] == 2
    assert report["summary"]["required_priorities"] == ["P1"]
    assert report["summary"]["replay_ready"] == 1
    assert report["summary"]["actual_replay_ready"] == 1
    assert "task-mt0wdfjx4y91c-fixed-reference-01" in report["actual_replay_ready_cases"]
    assert report["summary"]["coverage_debt"] == 0
    assert report["active_scope"]["name"] == "post-12-case-retirement"

    actual_required = run(
        VALIDATOR,
        "--matrix", str(MATRIX),
        "--strict",
        "--require-actual-replay",
    )
    assert actual_required.returncode == 0, actual_required.stdout + actual_required.stderr
    actual_report = json.loads(actual_required.stdout)
    assert actual_report["valid"] is True

    full = run(SELECTOR, "--matrix", str(MATRIX), "--full")
    assert full.returncode == 0, full.stdout + full.stderr
    full_report = json.loads(full.stdout)
    assert len(full_report["selected_case_ids"]) == len(cases)
    assert set(full_report["selected_case_ids"]).isdisjoint(history_ids)
    assert set(full_report["active_scope"]["excluded_case_ids"]) == history_ids

    targeted = run(SELECTOR, "--matrix", str(MATRIX), "--category", "native-structure")
    assert targeted.returncode == 0, targeted.stdout + targeted.stderr
    targeted_report = json.loads(targeted.stdout)
    selected = set(targeted_report["selected_case_ids"])
    assert "task-mt0wdfjx4y91c-fixed-reference-01" in selected
    assert "unicom-goals-16x9-fixed-reference-01" in selected
    assert targeted_report["promotion_blocked_by_replay_debt"] is False

    with tempfile.TemporaryDirectory(prefix="case-selection-invalid-") as temp:
        leaked_path = Path(temp) / "matrix.json"
        leaked = copy.deepcopy(matrix)
        leaked["cases"].append({"case_id": sorted(history_ids)[0]})
        leaked_path.write_text(json.dumps(leaked, ensure_ascii=False), encoding="utf-8")
        leaked_result = run(SELECTOR, "--matrix", str(leaked_path), "--full")
        assert leaked_result.returncode != 0
        assert "archived case IDs" in leaked_result.stdout

    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "case-replay-12" not in ci
    assert "Build 12-case" not in ci
    assert "Replay 12-case" not in ci
    assert "Validate and select distillation case matrix" in ci

    with tempfile.TemporaryDirectory(prefix="case-matrix-invalid-") as temp:
        invalid_path = Path(temp) / "matrix.json"
        invalid = copy.deepcopy(matrix)
        invalid["cases"].append(copy.deepcopy(invalid["cases"][0]))
        invalid["cases"][0].pop("required_checks")
        invalid_path.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
        bad = run(VALIDATOR, "--matrix", str(invalid_path), "--strict")
        assert bad.returncode != 0
        bad_report = json.loads(bad.stdout)
        codes = {item["code"] for item in bad_report["errors"]}
        assert "duplicate_case_id" in codes
        assert "schema" in codes or "required_checks" in codes

    print("distillation case matrix: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
