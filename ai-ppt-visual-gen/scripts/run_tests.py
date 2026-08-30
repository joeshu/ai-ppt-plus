#!/usr/bin/env python3
"""Run the repository's self-contained regression tests and fixture checks.

This runner intentionally does not require pytest. Existing tests are small
executable regression programs, so they can run in a clean agent environment
with the same Python interpreter used by the pipeline.

Usage: run_tests.py [--report test-report.json] [--timeout-seconds N]
       [--parallel-workers N]
"""

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from atomic_output import atomic_write_json


def yaml_check(root: Path) -> dict:
    files = sorted((root / "evals").glob("*.yaml"))
    try:
        import yaml
    except ImportError as exc:
        return {"status": "unavailable", "valid": False, "issues": [{"code": "pyyaml_missing", "message": str(exc)}], "files": [str(path) for path in files]}
    issues = []
    for path in files:
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append({"code": "yaml_parse_failed", "file": str(path), "message": f"{type(exc).__name__}: {exc}"})
    return {"status": "passed" if not issues else "failed", "valid": not issues, "files": [str(path) for path in files], "issues": issues}


def as_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run_one(test: Path, root: Path, timeout_seconds: int) -> dict:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, str(test)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        result = {
            "test": str(test.relative_to(root)),
            "status": "passed" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "stdout": as_text(completed.stdout),
            "stderr": as_text(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "test": str(test.relative_to(root)),
            "status": "failed",
            "returncode": 124,
            "stdout": as_text(exc.stdout),
            "stderr": as_text(exc.stderr) + f"\ntimed out after {timeout_seconds}s",
        }
    result["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--parallel-workers", type=int, default=4, help="maximum test subprocesses to run concurrently")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.parallel_workers < 1:
        print(json.dumps({"schema": "ai-ppt-plus/test-run/v1", "valid": False, "status": "failed", "failed": ["parallel_workers_invalid"]}, ensure_ascii=False))
        return 2
    tests = sorted((root / "tests").glob("test_*.py"))
    worker_count = min(args.parallel_workers, max(1, len(tests)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        # executor.map preserves the sorted test order in the report while
        # allowing independent subprocesses to overlap.
        results = list(executor.map(lambda test: run_one(test, root, args.timeout_seconds), tests))

    fixture = yaml_check(root)
    failed = [item["test"] for item in results if item["status"] != "passed"]
    if not fixture["valid"]:
        failed.append("evals/*.yaml")
    output = {
        "schema": "ai-ppt-plus/test-run/v1",
        "valid": not failed,
        "status": "passed" if not failed else "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "execution": {"parallel_workers": worker_count, "tests_total": len(results), "duration_ms": round(sum(float(item.get("duration_ms", 0) or 0) for item in results), 3)},
        "tests": results,
        "fixture_validation": fixture,
        "failed": failed,
    }
    if args.report:
        report = Path(args.report)
        atomic_write_json(report.resolve(), output)
    print(json.dumps(output, ensure_ascii=False))
    return 0 if output["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
