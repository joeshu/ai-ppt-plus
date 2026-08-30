#!/usr/bin/env python3
"""Regression coverage for explicit environment capability gates."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    contract = json.loads((ROOT / "assets" / "environment-contract.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="environment-contract-") as temp:
        root = Path(temp)
        capabilities = {name: {"available": True} for name in contract["required_capabilities"]}
        report = root / "environment-report.json"
        write_json(report, {"python": "3.12.1", "capabilities": capabilities})
        output = root / "environment-validation.json"
        command = [
            sys.executable, "scripts/validate_environment_contract.py",
            "--report", str(report), "--output", str(output),
        ]
        valid = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert valid.returncode == 0, valid.stdout + valid.stderr
        broken = json.loads(report.read_text(encoding="utf-8"))
        broken["capabilities"][contract["required_capabilities"][0]]["available"] = False
        write_json(report, broken)
        invalid = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert invalid.returncode == 2 and "required_capability_unavailable" in invalid.stdout, invalid.stdout

    print("environment contract gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
