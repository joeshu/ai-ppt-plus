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


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="capability-status-") as folder:
        root = Path(folder)
        engineering = root / "engineering.json"
        evidence = root / "evidence.json"
        host = root / "host.json"
        output = root / "status.json"
        write(engineering, {"strict_gate": {"passed": True}})
        write(evidence, {"valid": True, "human_visual_review_required": True})
        result = subprocess.run([
            sys.executable, "scripts/build_reconstruction_capability_status.py",
            "--engineering-report", str(engineering),
            "--four-evidence-report", str(evidence),
            "--output", str(output),
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        status = json.loads(output.read_text(encoding="utf-8"))
        assert status["engineering_gate"]["status"] == "passed"
        assert status["visual_evidence"]["status"] == "evidence-ready"
        assert status["host_validation"]["status"] == "pending"
        assert status["release_eligible"] is False

        write(evidence, {"valid": True, "human_visual_review_status": "passed"})
        write(host, {"valid": True, "status": "passed"})
        result = subprocess.run([
            sys.executable, "scripts/build_reconstruction_capability_status.py",
            "--engineering-report", str(engineering),
            "--four-evidence-report", str(evidence),
            "--host-validation-report", str(host),
            "--output", str(output),
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        status = json.loads(output.read_text(encoding="utf-8"))
        assert status["release_eligible"] is True
        assert status["visual_evidence"]["status"] == "confirmed"
        assert status["host_validation"]["status"] == "passed"
    print("reconstruction capability status: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
