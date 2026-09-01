#!/usr/bin/env python3
"""Approve one human-confirmed candidate and immediately run case ingestion.

This is the explicit local/CI driver for the same boundary used by the
scheduled GitHub Action: human approval first, then hash-bound dataset export
and CPU retrieval indexing.  It never invents approval and it never promotes
model weights.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SCRIPT_DIR = Path(__file__).resolve().parent
APPROVAL_SCRIPT = SCRIPT_DIR / "training_export.py"
CYCLE_SCRIPT = SCRIPT_DIR / "run_training_cycle.py"
REPORT_SCHEMA = "ai-ppt-plus/approved-case-ingestion/v1"


def _run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {"command": command, "returncode": completed.returncode, "stdout_tail": completed.stdout[-2000:], "stderr_tail": completed.stderr[-2000:]}


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    report_path = Path(args.report).resolve()
    registry = Path(args.registry).resolve()
    approval_command = [
        sys.executable,
        str(APPROVAL_SCRIPT),
        "approve-case",
        "--registry", str(registry),
        "--case-id", args.case_id,
        "--candidate-id", args.candidate_id,
        "--approved-by", args.approved_by,
        "--approval-note", args.approval_note,
        "--human-confirmed",
    ]
    approval = _run(approval_command)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": "blocked",
        "registry": str(registry),
        "case_id": args.case_id,
        "candidate_id": args.candidate_id,
        "human_confirmed": True,
        "approval": approval,
        "cycle": None,
        "next_action": None,
    }
    if approval["returncode"] != 0:
        report["code"] = "approval-blocked"
        report["next_action"] = "Fix the fresh score/report evidence and obtain explicit human approval."
        atomic_write_json(report_path, report)
        return report, 2
    cycle_command = [
        sys.executable,
        str(CYCLE_SCRIPT),
        "--registry", str(registry),
        "--output", str(Path(args.output).resolve()),
        "--manifest", str(Path(args.manifest).resolve()),
        "--materialize-dir", str(Path(args.materialize_dir).resolve()),
        "--report", str(Path(args.cycle_report).resolve()),
        "--retrieval-index", str(Path(args.retrieval_index).resolve()),
        "--retrieval-evaluation", str(Path(args.retrieval_evaluation).resolve()),
        "--split-seed", args.split_seed,
        "--require-approved",
    ]
    if args.trainer_command:
        cycle_command.extend(["--trainer-command", args.trainer_command])
    if args.require_trainer:
        cycle_command.append("--require-trainer")
    cycle = _run(cycle_command)
    report["cycle"] = cycle
    report["cycle_report"] = str(Path(args.cycle_report).resolve())
    report["status"] = "ingested" if cycle["returncode"] == 0 else "blocked"
    report["code"] = "ingestion-complete" if cycle["returncode"] == 0 else "ingestion-blocked"
    report["next_action"] = "Run independent evaluation before any model promotion." if cycle["returncode"] == 0 else "Inspect the cycle report and resolve the blocked export/retrieval stage."
    atomic_write_json(report_path, report)
    return report, 0 if cycle["returncode"] == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approval-note", required=True)
    parser.add_argument("--human-confirmed", action="store_true", required=True)
    parser.add_argument("--output", default="build/ai-ppt-editable/training.jsonl")
    parser.add_argument("--manifest", default="build/ai-ppt-editable/dataset-manifest.json")
    parser.add_argument("--materialize-dir", default="build/ai-ppt-editable/artifacts")
    parser.add_argument("--report", default="build/ai-ppt-editable/approved-case-ingestion.json")
    parser.add_argument("--cycle-report", default="build/ai-ppt-editable/training-cycle-report.json")
    parser.add_argument("--retrieval-index", default="build/ai-ppt-editable/retrieval-index.json")
    parser.add_argument("--retrieval-evaluation", default="build/ai-ppt-editable/retrieval-evaluation.json")
    parser.add_argument("--split-seed", default="ai-ppt-editable-v1")
    parser.add_argument("--trainer-command")
    parser.add_argument("--require-trainer", action="store_true")
    args = parser.parse_args()
    try:
        report, code = run(args)
        print(json.dumps({"schema": REPORT_SCHEMA, "status": report["status"], "code": report.get("code"), "report": str(Path(args.report).resolve())}, ensure_ascii=False))
        return code
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report = {"schema": REPORT_SCHEMA, "status": "blocked", "code": "approved_case_ingestion_failed", "message": str(exc)}
        atomic_write_json(Path(args.report).resolve(), report)
        print(json.dumps(report, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
