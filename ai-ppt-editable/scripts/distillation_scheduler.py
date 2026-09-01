#!/usr/bin/env python3
"""Choose the next safe action in the CPU distillation loop.

This is a policy engine, not a model trainer. It makes the loop self-driving
by converting the latest cycle report and bounded history into one explicit
next action, with a retry budget and human/escalation boundaries.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/distillation-scheduler-decision/v1"


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def choose(report: dict[str, Any], history: list[dict[str, Any]], *, max_attempts: int, max_repair_rounds: int) -> dict[str, Any]:
    attempts = len([item for item in history if item.get("action") in {"repair-and-rerun", "run-cycle"}])
    repair_round = max([int(item.get("repair_round", 0) or 0) for item in history] + [0])
    status = str(report.get("status") or "unknown")
    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    if attempts >= max_attempts or repair_round >= max_repair_rounds:
        action, reason = "escalate-human", "bounded repair budget exhausted"
    elif status == "blocked":
        action, reason = "repair-and-rerun", "latest gate is blocked"
    elif status in {"waiting-for-approval", "waiting-for-human-approval"} or report.get("human_approval_required") is True:
        action, reason = "request-human-approval", "machine evidence is ready but approval remains human-owned"
    elif status == "prepared" and report.get("trainer", {}).get("configured") is True:
        action, reason = "run-external-trainer", "dataset and CPU retrieval evidence are prepared"
    elif status == "prepared":
        action, reason = "collect-more-approved-cases", "CPU retrieval is ready; no trusted weight trainer is configured"
    elif status == "trained-candidate":
        action, reason = "request-human-promotion", "trainer output must be evaluated before promotion"
    elif status == "skipped":
        action, reason = "collect-more-approved-cases", "no eligible approved case was available"
    else:
        action, reason = "run-cycle", "run the declared deterministic gates"
    owner = None
    if issues:
        first = issues[0] if isinstance(issues[0], dict) else {}
        owner = first.get("owner") or first.get("code")
    return {
        "schema": SCHEMA,
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "reason": reason,
        "status_observed": status,
        "repair_owner": owner,
        "repair_round": repair_round + (1 if action == "repair-and-rerun" else 0),
        "budget": {"attempts_used": attempts, "max_attempts": max_attempts, "max_repair_rounds": max_repair_rounds, "remaining_attempts": max(0, max_attempts - attempts)},
        "human_boundary": "approval-and-promotion-never-automated",
        "safe_to_auto_apply": action in {"run-cycle", "repair-and-rerun"},
        "release_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-attempts", type=int, default=6)
    parser.add_argument("--max-repair-rounds", type=int, default=3)
    args = parser.parse_args()
    try:
        report = read_json(Path(args.report).resolve(), {})
        history = read_json(Path(args.history).resolve(), [])
        if not isinstance(report, dict) or not isinstance(history, list):
            raise ValueError("report must be an object and history must be an array")
        decision = choose(report, history, max_attempts=max(1, args.max_attempts), max_repair_rounds=max(1, args.max_repair_rounds))
        updated_history = history + [{"action": decision["action"], "status": decision["status_observed"], "repair_round": decision["repair_round"], "generated_at": decision["generated_at"]}]
        atomic_write_json(Path(args.output).resolve(), decision)
        atomic_write_json(Path(args.history).resolve(), updated_history)
        print(json.dumps(decision, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": SCHEMA, "valid": False, "status": "blocked", "code": "scheduler_failed", "message": str(exc)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
