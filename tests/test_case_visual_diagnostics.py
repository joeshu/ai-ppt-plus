#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    output = ROOT / ".distillation" / "case-visual-diagnostics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([
        sys.executable,
        "evals/case-replay-12/diagnose_visual_gap.py",
        "--candidate-evaluation", "evals/case-replay-12/candidate-evaluation.json",
        "--output", str(output),
    ], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.is_file() and output.stat().st_size > 0
    print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
