#!/usr/bin/env python3
"""Regression tests for the unattended distillation improvement gate."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_distillation_improvement.py"


def run_validator(baseline: dict, candidate: dict, *, case_spec: dict | None = None) -> tuple[int, dict]:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        baseline_path = work / "baseline.json"
        candidate_path = work / "candidate.json"
        report_path = work / "report.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        command = [
            sys.executable,
            str(VALIDATOR),
            "--baseline",
            str(baseline_path),
            "--candidate",
            str(candidate_path),
            "--mode",
            "replay" if case_spec else "gates",
            "--report",
            str(report_path),
        ]
        if case_spec:
            case_path = work / "case.json"
            case_path.write_text(json.dumps(case_spec), encoding="utf-8")
            command.extend(["--case-spec", str(case_path)])
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        return completed.returncode, json.loads(report_path.read_text(encoding="utf-8"))


def gate(status: str, gate_id: str = "route-contract") -> dict:
    return {"id": gate_id, "status": status}


def base_pair() -> tuple[dict, dict]:
    baseline = {
        "schema": "ai-ppt-plus/distillation-evaluation/v1",
        "case_id": "route-suite",
        "status": "failed",
        "valid": False,
        "failure_codes": ["route-contract"],
        "metrics": {"failed_gate_count": 1, "native_tables": 0},
        "gates": [gate("failed")],
    }
    candidate = {
        "schema": "ai-ppt-plus/distillation-evaluation/v1",
        "case_id": "route-suite",
        "status": "passed",
        "valid": True,
        "behavioral_change": True,
        "changed_files": ["SKILL.md"],
        "metrics": {"failed_gate_count": 0, "native_tables": 0},
        "gates": [gate("passed")],
    }
    return baseline, candidate


def main() -> int:
    baseline, candidate = base_pair()
    code, report = run_validator(baseline, candidate)
    assert code == 0, report
    assert report["promotion"] == "improved", report

    no_change = dict(candidate, behavioral_change=False, changed_files=[])
    code, report = run_validator(baseline, no_change)
    assert code != 0 and report["promotion"] == "no-improvement", report

    regression = dict(candidate, metrics={"failed_gate_count": 0, "native_tables": -1})
    code, report = run_validator(baseline, regression)
    assert code != 0 and not report["valid"], report

    case_spec = {
        "expected": {
            "native_tables": 2,
            "native_table_shapes": ["policy-fee-table", "monthly-incentive-table"],
            "native_panel_groups": True,
            "formal_text_in_raster": False,
        }
    }
    replay_baseline = dict(baseline, case_id="social-channel-commission-native-01")
    replay_candidate = dict(
        candidate,
        case_id="social-channel-commission-native-01",
        observed={
            "native_tables": 2,
            "native_table_shapes": ["policy-fee-table", "monthly-incentive-table"],
            "native_panel_groups": True,
            "formal_text_in_raster": False,
        },
    )
    code, report = run_validator(replay_baseline, replay_candidate, case_spec=case_spec)
    assert code == 0 and report["promotion"] == "improved", report

    missing_replay = dict(replay_candidate)
    missing_replay["observed"] = dict(replay_candidate["observed"], native_panel_groups=False)
    code, report = run_validator(replay_baseline, missing_replay, case_spec=case_spec)
    assert code != 0 and not report["valid"], report
    print("distillation improvement gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
