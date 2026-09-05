#!/usr/bin/env python3
"""Regression coverage for strict reference-reconstruction P1 gates."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, script, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="editable-p1-gates-") as temp:
        root = Path(temp)
        reference = root / "reference.png"
        Image.new("RGB", (160, 90), (20, 40, 80)).save(reference)
        rendered = root / "rendered"
        rendered.mkdir()
        Image.new("RGB", (160, 90), (20, 40, 80)).save(rendered / "slide-1.png")
        canvas_report = root / "canvas-report.json"
        result = run("scripts/validate_canvas_evidence.py", "--reference", str(reference), "--render-dir", str(rendered), "--expected-pages", "1", "--strict", "--report", str(canvas_report))
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(canvas_report.read_text(encoding="utf-8"))["exact_canvas"] is True

        deck = root / "deck.pptx"
        deck.write_bytes(b"pptx-test")
        screenshot = root / "slide-1.png"
        Image.new("RGB", (160, 90), (20, 40, 80)).save(screenshot)
        evidence = root / "host-evidence.json"
        write_json(evidence, {"schema": "ai-ppt-plus/host-validation/v1", "status": "passed", "deck_sha256": hashlib.sha256(deck.read_bytes()).hexdigest(), "host": {"kind": "powerpoint", "name": "Microsoft PowerPoint", "version": "test", "platform": "test"}, "reviewer": "p1-test", "confirmed_at": "2026-09-05T00:00:00Z", "checked_slides": [1], "checks": {"opened": True, "layout": True, "typography": True, "overflow": True, "editability": True, "visual_fidelity": True}, "screenshots": [{"slide_no": 1, "path": str(screenshot), "sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest()}]})
        host_report = root / "host-report.json"
        result = run("scripts/validate_host_validation.py", str(evidence), "--deck", str(deck), "--expected-pages", "1", "--strict", "--report", str(host_report))
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(host_report.read_text(encoding="utf-8"))["valid"] is True
        print("editable P1 reconstruction gates: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
