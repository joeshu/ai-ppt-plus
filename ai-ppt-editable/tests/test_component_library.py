#!/usr/bin/env python3
"""Regression test for the reusable component registry."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="component-library-") as temp:
        report = Path(temp) / "report.json"
        valid = subprocess.run([sys.executable, "scripts/validate_component_library.py", "assets/component-library.template.json", "--report", str(report)], cwd=ROOT, capture_output=True, text=True)
        assert valid.returncode == 0, valid.stdout + valid.stderr
        data = json.loads((ROOT / "assets/component-library.template.json").read_text(encoding="utf-8"))
        data["components"].append(dict(data["components"][0]))
        bad = Path(temp) / "bad.json"
        bad.write_text(json.dumps(data), encoding="utf-8")
        failed = subprocess.run([sys.executable, "scripts/validate_component_library.py", str(bad), "--report", str(report)], cwd=ROOT, capture_output=True, text=True)
        assert failed.returncode == 2 and "component_id_duplicate" in failed.stdout
    print("component library contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
