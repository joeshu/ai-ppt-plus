#!/usr/bin/env python3
"""Run the repository's self-contained regression tests and fixture checks.

This runner intentionally does not require pytest. Existing tests are small
executable regression programs, so they can run in a clean agent environment
with the same Python interpreter used by the pipeline.

Usage: run_tests.py [--report test-report.json] [--timeout-seconds N]
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    results = []
    for test in sorted((root / "tests").glob("test_*.py")):
        try:
            completed = subprocess.run(
                [sys.executable, str(test)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=args.timeout_seconds,
                check=False,
            )
            result = {
                "test": str(test.relative_to(root)),
                "status": "passed" if completed.returncode == 0 else "failed",
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except subprocess.TimeoutExpired as exc:
            result = {
                "test": str(test.relative_to(root)),
                "status": "failed",
                "returncode": 124,
                "stdout": exc.stdout or "",
                "stderr": (exc.stderr or "") + f"\ntimed out after {args.timeout_seconds}s",
            }
        results.append(result)

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
        "tests": results,
        "fixture_validation": fixture,
        "failed": failed,
    }
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))
    return 0 if output["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
