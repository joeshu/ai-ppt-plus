#!/usr/bin/env python3
"""Regression tests for the automatic training-cycle driver."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_training_cycle.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="training-cycle-") as temp:
        root = Path(temp)
        report = root / "cycle.json"
        skipped = run("--registry", str(root / "missing.json"), "--report", str(report))
        assert skipped.returncode == 0, skipped.stdout + skipped.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["status"] == "skipped" and data["code"] == "registry_not_found"

        registry = root / "cases.json"
        registry.write_text(json.dumps({"schema": "ai-ppt-plus/distillation-case-registry/v1", "version": 1, "cases": []}), encoding="utf-8")
        waiting = run("--registry", str(registry), "--report", str(report))
        assert waiting.returncode == 0, waiting.stdout + waiting.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["status"] == "waiting-human-approval" and data["retrieval_ready"] is False

        required = run("--registry", str(registry), "--report", str(report), "--require-approved")
        assert required.returncode == 2, required.stdout + required.stderr

    print("automatic training cycle: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
