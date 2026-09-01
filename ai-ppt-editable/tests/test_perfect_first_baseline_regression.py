#!/usr/bin/env python3
"""Keep the shipped perfect-first reconstruction from silently regressing."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
BASELINE = REPO_ROOT / "image2pptx_runs/baselines/R1_20260828_53_5"
DECK = BASELINE / "deck/R1_20260828_53_5_unicom_dual_terminal_editable.pptx"
REFERENCE = BASELINE / "source/reference-01.jpeg"


def main() -> int:
    assert DECK.is_file() and REFERENCE.is_file()
    with tempfile.TemporaryDirectory(prefix="perfect-first-baseline-") as temp:
        report = Path(temp) / "inspection.json"
        completed = subprocess.run(
            [sys.executable, "scripts/inspect_pptx.py", str(DECK), "--report", str(report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        slide = data["slides"][0]
        assert data["ok"] is True
        assert data["slide_count"] == 1 and data["is_16_9"] is True
        assert slide["text_objects"] >= 20
        assert slide["pictures"] >= 10
        assert slide["graphic_frames"] == 0 and slide["charts"] == 0
        assert slide["off_canvas"] == 0
        assert slide["fonts"] == ["Noto Sans CJK SC"]
        assert data["embedded_fonts"]["present"] is True
    print("perfect-first baseline regression: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
