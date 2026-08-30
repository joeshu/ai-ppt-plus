#!/usr/bin/env python3
"""Smoke-test the pinned perfect-source parity gate."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="perfect-sync-") as temp:
        report = Path(temp) / "sync-validation.json"
        checked = subprocess.run(
            [sys.executable, "scripts/validate_perfect_sync.py", "--report", str(report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True, data
        assert data["source"]["repository"] == "joeshu/ai-ppt-plus", data
        assert data["source"]["ref"] == "完美第一版", data
        assert data["source"]["commit"] == "d5dec0588fe87581112cbe1498ad4dac44f402e4", data
        assert data["synced_file_count"] >= 177, data
    print("perfect-source parity gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
