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
    assert len(cases) >= 10
    assert {case["priority"] for case in cases} == {"P0", "P1", "P2"}
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert matrix["policy"]["static_sentinel_never_promotes"] is True

    validation = run(VALIDATOR, "--matrix", str(MATRIX), "--strict")
    assert validation.returncode == 0, validation.stdout + validation.stderr
    report = json.loads(validation.stdout)
    assert report["valid"] is True, report
    assert report["summary"]["replay_ready"] >= 1
    assert report["summary"]["actual_replay_ready"] == 0
    assert report["summary"]["coverage_debt"] >= 1
    assert "native-table-merge-richtext-01" in report["replay_ready_cases"]

    actual_required = run(
        VALIDATOR,
        "--matrix", str(MATRIX),
        "--strict",
        "--require-actual-replay",
    )
    assert actual_required.returncode != 0
    actual_report = json.loads(actual_required.stdout)
    assert any(item["code"] == "actual_replay_required" for item in actual_report["errors"])

    full = run(SELECTOR, "--matrix", str(MATRIX), "--full")
    assert full.returncode == 0, full.stdout + full.stderr
    full_report = json.loads(full.stdout)
    assert len(full_report["selected_case_ids"]) == len(cases)

    targeted = run(SELECTOR, "--matrix", str(MATRIX), "--category", "native-structure")
    assert targeted.returncode == 0, targeted.stdout + targeted.stderr
    targeted_report = json.loads(targeted.stdout)
    selected = set(targeted_report["selected_case_ids"])
    assert "native-table-merge-richtext-01" in selected
    assert "route-editable-default-01" in selected  # P0 safety inclusion.
    assert targeted_report["promotion_blocked_by_replay_debt"] is True

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
