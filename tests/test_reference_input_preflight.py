#!/usr/bin/env python3
"""Regression coverage for bounded missing-path and upload-suffix resolution."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reference_input_preflight.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        workspace = Path(raw)
        upload = workspace / "upload"
        upload.mkdir()
        first = upload / "reference (1).png"
        Image.new("RGB", (1536, 864), (20, 30, 40)).save(first)
        report = workspace / "resolved.json"
        completed = run(
            "--input", str(workspace / "reference.png"),
            "--search-root", str(upload),
            "--expected-count", "1",
            "--expected-ratio", str(16 / 9),
            "--strict",
            "--output", str(report),
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(report.read_text(encoding="utf-8"))
        assert result["valid"] is True
        assert result["inputs"][0]["filename"] == first.name
        assert result["inputs"][0]["width"] == 1536
        assert len(result["inputs"][0]["sha256"]) == 64

        # A second automatic rename with different bytes must block rather than
        # silently guessing which upload is the requested page.
        Image.new("RGB", (1536, 864), (90, 80, 70)).save(upload / "reference (2).png")
        ambiguous = workspace / "ambiguous.json"
        completed = run(
            "--input", str(workspace / "reference.png"),
            "--search-root", str(upload),
            "--expected-count", "1",
            "--output", str(ambiguous),
        )
        assert completed.returncode != 0
        result = json.loads(ambiguous.read_text(encoding="utf-8"))
        assert result["valid"] is False
        assert any(item["code"] == "ambiguous_input_hashes" for item in result["issues"])
    print("reference input preflight: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
