#!/usr/bin/env python3
"""Drive the approved-case export and optional model-trainer hook.

This is an orchestration boundary, not a hidden trainer.  It turns a case
registry into a hash-bound JSONL dataset, records an auditable cycle report,
and invokes a deliberately explicit external trainer only when one is
configured by the operator or workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


CYCLE_SCHEMA = "ai-ppt-plus/distillation-training-cycle/v1"
REGISTRY_SCHEMA = "ai-ppt-plus/distillation-case-registry/v1"
SCRIPT = Path(__file__).resolve().with_name("training_export.py")
RETRIEVAL_SCRIPT = Path(__file__).resolve().with_name("build_retrieval_index.py")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def approved_count(registry: dict[str, Any]) -> int:
    count = 0
    for case in registry.get("cases") or []:
        if not isinstance(case, dict):
            continue
        for candidate in case.get("candidates") or []:
            if isinstance(candidate, dict) and candidate.get("training_eligible") is True and candidate.get("status") == "human-approved":
                count += 1
    return count


def write_report(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    atomic_write_json(path, report)
    return report


def base_report(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema": CYCLE_SCHEMA,
        "cycle_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "blocked",
        "registry": str(Path(args.registry).resolve()),
        "dataset": {
            "records_path": str(Path(args.output).resolve()),
            "manifest_path": str(Path(args.manifest).resolve()),
            "materialize_dir": str(Path(args.materialize_dir).resolve()) if args.materialize_dir else None,
        },
        "approved_candidate_count": 0,
        "retrieval_ready": False,
        "retrieval": {
            "index_path": str(Path(args.retrieval_index).resolve()),
            "evaluation_path": str(Path(args.retrieval_evaluation).resolve()),
            "status": "not-started",
        },
        "model_training_status": "not-started",
        "model_promotion_status": "pending-human-approval",
        "trainer": {"configured": bool(args.trainer_command), "status": "not-configured" if not args.trainer_command else "configured"},
        "human_approval_required": True,
        "release_eligible": False,
        "issues": [],
    }


def run_cycle(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    report_path = Path(args.report).resolve()
    report = base_report(args)
    registry_path = Path(args.registry).resolve()
    if not registry_path.is_file():
        report["status"] = "skipped"
        report["code"] = "registry_not_found"
        report["issues"].append({"code": "registry_not_found", "path": str(registry_path)})
        report["next_action"] = "Export is waiting for a case registry containing human-approved candidates."
        code = 2 if args.require_approved else 0
        return write_report(report_path, report), code

    try:
        registry = read_json(registry_path)
        if registry.get("schema") != REGISTRY_SCHEMA or not isinstance(registry.get("cases"), list):
            raise ValueError(f"registry must use {REGISTRY_SCHEMA}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report["code"] = "registry_invalid"
        report["issues"].append({"code": "registry_invalid", "message": str(exc)})
        return write_report(report_path, report), 2

    count = approved_count(registry)
    report["approved_candidate_count"] = count
    if count == 0:
        report["status"] = "waiting-human-approval"
        report["code"] = "no-approved-cases"
        report["issues"].append({"code": "no-approved-cases", "message": "No explicit human-approved candidate is eligible for export."})
        report["next_action"] = "Run approve-case after a person checks visual fidelity, formal content, and editability."
        code = 2 if args.require_approved else 0
        return write_report(report_path, report), code

    command = [
        sys.executable,
        str(SCRIPT),
        "export",
        "--registry",
        str(registry_path),
        "--output",
        str(Path(args.output).resolve()),
        "--manifest",
        str(Path(args.manifest).resolve()),
        "--split-seed",
        args.split_seed,
    ]
    if args.materialize_dir:
        command.extend(["--materialize-dir", str(Path(args.materialize_dir).resolve())])
    exported = subprocess.run(command, capture_output=True, text=True, check=False)
    report["export"] = {
        "returncode": exported.returncode,
        "stdout_tail": exported.stdout[-2000:],
        "stderr_tail": exported.stderr[-2000:],
    }
    if exported.returncode != 0:
        report["code"] = "dataset-export-blocked"
        report["issues"].append({"code": "dataset-export-blocked", "returncode": exported.returncode})
        return write_report(report_path, report), 2

    try:
        manifest = read_json(Path(args.manifest).resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report["code"] = "dataset-manifest-invalid"
        report["issues"].append({"code": "dataset-manifest-invalid", "message": str(exc)})
        return write_report(report_path, report), 2
    report["retrieval_ready"] = manifest.get("retrieval_ready") is True
    report["dataset_records_sha256"] = manifest.get("records_sha256")
    report["dataset_record_count"] = manifest.get("record_count", 0)
    if report["retrieval_ready"] is not True:
        report["status"] = "blocked"
        report["code"] = "dataset-not-retrieval-ready"
        report["issues"].append({"code": "dataset-not-retrieval-ready"})
        return write_report(report_path, report), 2

    retrieval_command = [
        sys.executable,
        str(RETRIEVAL_SCRIPT),
        "--records",
        str(Path(args.output).resolve()),
        "--manifest",
        str(Path(args.manifest).resolve()),
        "--index",
        str(Path(args.retrieval_index).resolve()),
        "--evaluation",
        str(Path(args.retrieval_evaluation).resolve()),
    ]
    retrieval = subprocess.run(retrieval_command, capture_output=True, text=True, check=False)
    retrieval_evaluation: dict[str, Any] = {}
    if Path(args.retrieval_evaluation).resolve().is_file():
        try:
            retrieval_evaluation = read_json(Path(args.retrieval_evaluation).resolve())
        except (OSError, ValueError, json.JSONDecodeError):
            retrieval_evaluation = {}
    report["retrieval"] = {
        "index_path": str(Path(args.retrieval_index).resolve()),
        "evaluation_path": str(Path(args.retrieval_evaluation).resolve()),
        "returncode": retrieval.returncode,
        "status": retrieval_evaluation.get("status") if retrieval.returncode == 0 else "blocked",
        "stdout_tail": retrieval.stdout[-2000:],
        "stderr_tail": retrieval.stderr[-2000:],
    }
    if retrieval.returncode != 0:
        report["status"] = "blocked"
        report["code"] = "retrieval-index-blocked"
        report["issues"].append({"code": "retrieval-index-blocked", "returncode": retrieval.returncode})
        return write_report(report_path, report), 2

    trainer_command = args.trainer_command
    if not trainer_command:
        report["status"] = "prepared"
        report["code"] = "trainer-not-configured"
        report["model_training_status"] = "not-configured"
        report["next_action"] = "Provide a trusted model-specific trainer command or service adapter; do not promote weights automatically."
        code = 2 if args.require_trainer else 0
        return write_report(report_path, report), code

    tokens = shlex.split(trainer_command)
    if not tokens:
        report["status"] = "blocked"
        report["code"] = "trainer-command-empty"
        report["issues"].append({"code": "trainer-command-empty"})
        return write_report(report_path, report), 2
    trainer_env = os.environ.copy()
    trainer_env["AI_PPT_DATASET_MANIFEST"] = str(Path(args.manifest).resolve())
    trainer_env["AI_PPT_DATASET_RECORDS"] = str(Path(args.output).resolve())
    trainer_env["AI_PPT_RETRIEVAL_INDEX"] = str(Path(args.retrieval_index).resolve())
    trained = subprocess.run(tokens, cwd=Path.cwd(), env=trainer_env, capture_output=True, text=True, check=False)
    report["trainer"] = {
        "configured": True,
        "status": "passed" if trained.returncode == 0 else "failed",
        "returncode": trained.returncode,
        "stdout_tail": trained.stdout[-2000:],
        "stderr_tail": trained.stderr[-2000:],
    }
    if trained.returncode != 0:
        report["status"] = "blocked"
        report["code"] = "trainer-failed"
        report["model_training_status"] = "failed"
        report["issues"].append({"code": "trainer-failed", "returncode": trained.returncode})
        return write_report(report_path, report), 2
    report["status"] = "trained-candidate"
    report["code"] = "trainer-passed-human-review-required"
    report["model_training_status"] = "candidate-produced"
    report["next_action"] = "Run independent model/deck evaluation and obtain human approval before promotion."
    return write_report(report_path, report), 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="datasets/ai-ppt-editable/cases.json")
    parser.add_argument("--output", default="build/ai-ppt-editable/training.jsonl")
    parser.add_argument("--manifest", default="build/ai-ppt-editable/dataset-manifest.json")
    parser.add_argument("--materialize-dir", default="build/ai-ppt-editable/artifacts")
    parser.add_argument("--report", default="build/ai-ppt-editable/training-cycle-report.json")
    parser.add_argument("--retrieval-index", default="build/ai-ppt-editable/retrieval-index.json")
    parser.add_argument("--retrieval-evaluation", default="build/ai-ppt-editable/retrieval-evaluation.json")
    parser.add_argument("--split-seed", default="ai-ppt-editable-v1")
    parser.add_argument("--trainer-command", default=os.environ.get("AI_PPT_TRAINER_COMMAND"))
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--require-trainer", action="store_true")
    args = parser.parse_args()
    try:
        report, code = run_cycle(args)
        print(json.dumps({"schema": CYCLE_SCHEMA, "status": report["status"], "code": report.get("code"), "report": str(Path(args.report).resolve()), "retrieval_ready": report["retrieval_ready"], "model_training_status": report["model_training_status"]}, ensure_ascii=False))
        return code
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        report = base_report(args)
        report["code"] = "training_cycle_failed"
        report["issues"].append({"code": "training_cycle_failed", "message": str(exc)})
        write_report(Path(args.report).resolve(), report)
        print(json.dumps({"schema": CYCLE_SCHEMA, "status": "blocked", "code": "training_cycle_failed", "message": str(exc)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
