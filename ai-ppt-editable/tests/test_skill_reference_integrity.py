#!/usr/bin/env python3
"""Regression coverage for fail-closed SKILL.md reference resolution."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_skill_references.py"


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        report = Path(raw) / "references.json"
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--skill-dir", str(ROOT), "--all-bundled", "--output", str(report)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(report.read_text(encoding="utf-8"))
        assert result["valid"] is True
        assert result["issues"] == []
        assert result["references"]
    print("skill reference integrity: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
