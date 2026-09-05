#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def run(output: Path, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, "scripts/build_reconstruction_capability_status.py", *args, "--output", str(output)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(output.read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="capability-status-") as folder:
        root = Path(folder)
        engineering = root / "engineering.json"
        visual = root / "visual.json"
        evidence = root / "evidence.json"
        desktop = root / "desktop.json"
        mobile = root / "mobile.json"
        legacy = root / "legacy.json"
        output = root / "status.json"
        write(engineering, {"strict_gate": {"passed": True}})
        write(visual, {"valid": True, "policy_version": "2026.09-rf006"})
        write(evidence, {"valid": True, "human_visual_review_required": True})

        # Technical-only evidence is no longer enough for engineering pass.
        status = run(output,
            "--engineering-report", str(engineering),
            "--four-evidence-report", str(evidence))
        assert status["engineering_gate"]["status"] == "blocked"
        assert status["engineering_gate"]["technical_status"] == "passed"
        assert status["engineering_gate"]["automated_visual_fidelity_status"] == "blocked"

        status = run(output,
            "--engineering-report", str(engineering),
            "--visual-fidelity-report", str(visual),
            "--four-evidence-report", str(evidence))
        assert status["engineering_gate"]["status"] == "passed"
        assert status["engineering_gate"]["automated_visual_fidelity_status"] == "passed"
        assert status["visual_evidence"]["status"] == "evidence-ready"
        assert status["host_validation"]["desktop"]["status"] == "pending"
        assert status["host_validation"]["ios"]["status"] == "pending"
        assert status["release_eligible"] is False

        # A legacy single-host report must never be enough for final release.
        write(evidence, {"valid": True, "human_visual_review_status": "passed"})
        write(legacy, {"valid": True, "status": "passed"})
        status = run(output,
            "--engineering-report", str(engineering),
            "--visual-fidelity-report", str(visual),
            "--four-evidence-report", str(evidence),
            "--host-validation-report", str(legacy))
        assert status["host_validation"]["legacy_single_host_present"] is True
        assert status["host_validation"]["legacy_single_host_sufficient"] is False
        assert status["release_eligible"] is False

        write(desktop, {"valid": True, "status": "passed", "host": {"profile": "desktop", "kind": "wps"}})
        write(mobile, {"valid": True, "status": "passed", "host": {"profile": "ios", "kind": "wps"}})
        status = run(output,
            "--engineering-report", str(engineering),
            "--visual-fidelity-report", str(visual),
            "--four-evidence-report", str(evidence),
            "--desktop-host-validation-report", str(desktop),
            "--mobile-host-validation-report", str(mobile))
        assert status["release_eligible"] is True
        assert status["visual_evidence"]["status"] == "confirmed"
        assert status["host_validation"]["desktop"]["status"] == "passed"
        assert status["host_validation"]["ios"]["status"] == "passed"
    print("reconstruction capability status: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
