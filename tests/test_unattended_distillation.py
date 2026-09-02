#!/usr/bin/env python3
"""Regression coverage for the bounded unattended distillation controller."""
from __future__ import annotations

import json
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

    print("unattended distillation controller: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
