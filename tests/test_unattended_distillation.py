#!/usr/bin/env python3
"""Regression coverage for the bounded unattended distillation controller."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "unattended_distillation_agent.py"
POLICY = ROOT / "assets" / "unattended-distillation-policy.json"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, capture_output=True, text=True, check=False)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="unattended-distillation-") as temp:
        root = Path(temp)
        input_dir = root / "input"
        report = input_dir / "ci-report.json"
        write_json(report, {
            "schema": "test/report/v1",
            "valid": False,
            "status": "failed",
            "issues": [{
                "severity": "blocker",
                "code": "routing_binding_mismatch",
                "message": "primary engine route mismatch",
            }],
        })
        analysis_path = root / "analysis.json"
        analyzed = run("analyze", "--repo-root", str(root), "--input-dir", str(input_dir), "--output", str(analysis_path))
        assert analyzed.returncode == 0, analyzed.stdout + analyzed.stderr
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        assert analysis["status"] == "issues-found"
        assert analysis["categories"] == ["routing"]

        (root / "SKILL.md").write_text("# test skill\n", encoding="utf-8")
        change_path = root / "change.json"
        applied = run(
            "apply",
            "--repo-root", str(root),
            "--policy", str(POLICY),
            "--analysis", str(analysis_path),
            "--output", str(change_path),
        )
        assert applied.returncode == 0, applied.stdout + applied.stderr
        change = json.loads(change_path.read_text(encoding="utf-8"))
        assert change["status"] == "changed"
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        assert "unattended-distillation:route-lock" in skill

        repeated_path = root / "repeated.json"
        repeated = run(
            "apply",
            "--repo-root", str(root),
            "--policy", str(POLICY),
            "--analysis", str(analysis_path),
            "--output", str(repeated_path),
        )
        assert repeated.returncode == 0, repeated.stdout + repeated.stderr
        assert json.loads(repeated_path.read_text(encoding="utf-8"))["status"] == "no-change"

        unknown = root / "unknown.json"
        write_json(unknown, {"valid": False, "status": "failed", "issues": [{"code": "mystery_failure", "message": "unclassified defect"}]})
        unknown_analysis = root / "unknown-analysis.json"
        analyzed_unknown = run("analyze", "--repo-root", str(root), "--input-dir", str(root), "--output", str(unknown_analysis))
        assert analyzed_unknown.returncode == 0, analyzed_unknown.stdout + analyzed_unknown.stderr
        unknown_data = json.loads(unknown_analysis.read_text(encoding="utf-8"))
        assert unknown_data["requires_manual"] is True

    # Exercise the production run path: a reproducible red baseline, an
    # allowlisted repair, a green candidate, and a positive improvement proof.
    with tempfile.TemporaryDirectory(prefix="unattended-distillation-run-") as temp:
        root = Path(temp)
        (root / "scripts").mkdir()
        shutil.copy2(SCRIPT, root / "scripts" / SCRIPT.name)
        shutil.copy2(ROOT / "scripts" / "validate_distillation_improvement.py", root / "scripts" / "validate_distillation_improvement.py")
        (root / "SKILL.md").write_text("# test skill\n", encoding="utf-8")
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        policy["gates"] = [{
            "id": "route-contract",
            "argv": [
                "python",
                "-c",
                "import pathlib,sys; sys.exit(0 if 'unattended-distillation:route-lock' in pathlib.Path('SKILL.md').read_text() else 1)",
            ],
            "timeout_seconds": 30,
        }]
        policy_path = root / "policy.json"
        write_json(policy_path, policy)
        input_dir = root / "input"
        write_json(input_dir / "failure.json", {
            "valid": False,
            "status": "failed",
            "issues": [{"code": "routing_binding_mismatch", "message": "route mismatch"}],
        })
        subprocess.run(["git", "init"], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "distillation test"], cwd=root, check=True)
        subprocess.run(["git", "add", "SKILL.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=root, capture_output=True, check=True)
        report_dir = root / "reports"
        result_path = root / "result.json"
        completed = run(
            "run",
            "--repo-root", str(root),
            "--input-dir", str(input_dir),
            "--report-dir", str(report_dir),
            "--policy", str(policy_path),
            "--output", str(result_path),
            "--require-improvement",
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["status"] == "passed", result
        assert result["promotion"] == "improved", result
        assert result["changed"] is True, result
        assert "unattended-distillation:route-lock" in (root / "SKILL.md").read_text(encoding="utf-8")

    print("unattended distillation controller: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
