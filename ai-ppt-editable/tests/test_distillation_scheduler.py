#!/usr/bin/env python3
"""Regression tests for bounded self-driving distillation policy."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "distillation_scheduler.py"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="scheduler-") as temp:
        root = Path(temp)
        report = root / "report.json"
        history = root / "history.json"
        output = root / "decision.json"
        report.write_text(json.dumps({"status": "blocked", "issues": [{"owner": "font", "code": "font_missing"}]}), encoding="utf-8")
        history.write_text("[]", encoding="utf-8")
        run = subprocess.run([sys.executable, str(SCRIPT), "--report", str(report), "--history", str(history), "--output", str(output)], capture_output=True, text=True, check=False)
        assert run.returncode == 0, run.stdout + run.stderr
        decision = json.loads(output.read_text(encoding="utf-8"))
        assert decision["action"] == "repair-and-rerun" and decision["repair_owner"] == "font"
        assert decision["safe_to_auto_apply"] is True

        report.write_text(json.dumps({"status": "prepared", "human_approval_required": True, "trainer": {"configured": False}}), encoding="utf-8")
        run = subprocess.run([sys.executable, str(SCRIPT), "--report", str(report), "--history", str(history), "--output", str(output)], capture_output=True, text=True, check=False)
        assert run.returncode == 0
        decision = json.loads(output.read_text(encoding="utf-8"))
        assert decision["action"] == "request-human-approval"
        assert decision["release_eligible"] is False
    print("distillation scheduler: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
