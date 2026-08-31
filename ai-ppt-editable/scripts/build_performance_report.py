#!/usr/bin/env python3
"""Build one normalized performance report from a pipeline result."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/performance-report/v1"


def _integer(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _repair_rounds(data: dict[str, Any], issue_log: dict[str, Any] | None, explicit: int | None) -> int:
    values = []
    if explicit is not None:
        values.append(_integer(explicit))
    execution = data.get("execution") if isinstance(data.get("execution"), dict) else {}
    values.append(_integer(execution.get("repair_rounds")))
    if isinstance(issue_log, dict):
        values.append(_integer(issue_log.get("repair_rounds")))
        for record in issue_log.get("issues") or []:
            if not isinstance(record, dict):
                continue
            values.append(_integer(record.get("repair_round")))
            history = record.get("repair_history")
            if isinstance(history, list):
                values.append(len(history))
    return max(values, default=0)


def build(pipeline_result: Path, output: Path, *, issue_log: Path | None = None, repair_round: int | None = None) -> dict[str, Any]:
    data = json.loads(pipeline_result.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pipeline result must be an object")
    execution = data.get("execution") if isinstance(data.get("execution"), dict) else {}
    steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    issue_data = None
    if issue_log and issue_log.is_file():
        loaded = json.loads(issue_log.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            issue_data = loaded

    task_hits = _integer(execution.get("cache_hits"))
    task_misses = _integer(execution.get("cache_misses"))
    page_cache = execution.get("page_cache") if isinstance(execution.get("page_cache"), dict) else {}
    page_hits = _integer(page_cache.get("hits"))
    page_misses = _integer(page_cache.get("misses"))
    retries = _integer(execution.get("retry_count")) if "retry_count" in execution else sum(
        _integer(step.get("retry_count")) for step in steps if isinstance(step, dict)
    )
    repair_rounds = _repair_rounds(data, issue_data, repair_round)
    durations = [
        {"name": step.get("name"), "duration_ms": float(step.get("duration_ms", 0) or 0), "cache_hit": step.get("cache_hit") is True}
        for step in steps
        if isinstance(step, dict) and step.get("name")
    ]
    durations.sort(key=lambda item: (-item["duration_ms"], item["name"]))
    report = {
        "schema": SCHEMA,
        "status": "passed",
        "run_id": data.get("run_id"),
        "project": data.get("project"),
        "deck": data.get("deck"),
        "deck_sha256": data.get("deck_sha256"),
        "validation_scope": data.get("validation_scope", "full"),
        "execution": {
            "mode": execution.get("mode"),
            "parallel_workers": _integer(execution.get("parallel_workers"), 1),
            "tasks_total": _integer(execution.get("tasks_total"), len(steps)),
            "cache_hits": task_hits,
            "cache_misses": task_misses,
            "cache_hit_rate": _ratio(task_hits, task_hits + task_misses),
            "page_cache": {
                "enabled": bool(page_cache.get("enabled")),
                "hits": page_hits,
                "misses": page_misses,
                "hit_rate": _ratio(page_hits, page_hits + page_misses),
                "stored": _integer(page_cache.get("stored")),
            },
            "wall_duration_ms": float(execution.get("duration_ms", 0) or 0),
            "task_duration_ms_sum": float(execution.get("task_duration_ms_sum", 0) or 0),
            "critical_path_ms": float(execution.get("critical_path_ms", 0) or 0),
            "retry_count": retries,
            "repair_rounds": repair_rounds,
            "affected_pages": execution.get("affected_pages", "all"),
            "affected_regions": execution.get("affected_regions", []),
        },
        "steps_by_duration": durations[:10],
        "step_count": len(steps),
        "failed_steps": data.get("failed_steps", []),
        "issue_log": str(issue_log.resolve()) if issue_log else None,
        "definitions": {
            "cache_hit_rate": "task cache hits / (task cache hits + task cache misses)",
            "page_cache_hit_rate": "page cache hits / (page cache hits + page cache misses)",
            "repair_rounds": "issue fix followed by re-render and re-validation; retries are excluded",
            "duration_sum_is_diagnostic": True,
        },
    }
    atomic_write_json(output.resolve(), report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline_result")
    parser.add_argument("--output", required=True)
    parser.add_argument("--issue-log")
    parser.add_argument("--repair-round", type=int)
    args = parser.parse_args()
    try:
        report = build(
            Path(args.pipeline_result).resolve(),
            Path(args.output).resolve(),
            issue_log=Path(args.issue_log).resolve() if args.issue_log else None,
            repair_round=args.repair_round,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "blocked", "valid": False, "code": "performance_report_failed", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": "passed", "valid": True, "output": str(Path(args.output).resolve()), "cache_hit_rate": report["execution"]["cache_hit_rate"], "repair_rounds": report["execution"]["repair_rounds"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
