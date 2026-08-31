#!/usr/bin/env python3
"""Regression coverage for P1 reliability and review contracts."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, script, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="p1-governance-") as temp:
        root = Path(temp)
        design = root / "design-system.yaml"
        design.write_text((ROOT / "assets/design-system.template.yaml").read_text(encoding="utf-8").replace("approval_status: draft", "approval_status: approved"), encoding="utf-8")
        design_check = run("scripts/validate_design_system.py", str(design), "--strict")
        assert design_check.returncode == 0, design_check.stdout + design_check.stderr
        issue_log = root / "issue-log.json"
        write_json(issue_log, {"schema": "ai-ppt-plus/issue-log/v1", "project_id": "p1", "revision": "R1", "issues": [{"id": "P1-001", "severity": "major", "status": "closed", "owner": "root", "trigger": "cache corruption", "root_cause": "unverified artifact", "fix": "hash and quarantine", "regression_test": "tests/test_pipeline_engine.py", "affected_stages": ["cache"], "resolved_revision": "R1"}]})
        issue_check = run("scripts/validate_issue_log.py", str(issue_log), "--strict")
        assert issue_check.returncode == 0, issue_check.stdout + issue_check.stderr
        open_log = json.loads(issue_log.read_text(encoding="utf-8")); open_log["issues"][0]["status"] = "open"; write_json(issue_log, open_log)
        issue_blocked = run("scripts/validate_issue_log.py", str(issue_log), "--strict")
        assert issue_blocked.returncode == 2 and "open_issues_block_strict" in issue_blocked.stdout, issue_blocked.stdout

        pipeline_result = root / "pipeline-result.json"
        write_json(pipeline_result, {"project": "p1", "run_id": "run-1", "run_dir": str(root), "technical_status": "passed", "human_review_status": "pending", "release_status": "blocked", "technical_valid": True, "release_eligible": False, "validation_scope": "full", "failed_steps": [], "steps": [], "execution": {"affected_pages": "all", "affected_regions": []}})
        review = run("scripts/build_review_package.py", str(pipeline_result), "--output", str(root / "review-package"))
        assert review.returncode == 0, review.stdout + review.stderr
        package = json.loads((root / "review-package/review-package.json").read_text(encoding="utf-8"))
        assert package["schema"] == "ai-ppt-plus/review-package/v1" and package["artifact_count"] >= 2
        print("root P1 governance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
