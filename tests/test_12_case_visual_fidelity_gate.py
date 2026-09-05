#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evals" / "case-replay-12" / "validate_candidate_visual_fidelity.py"


def run_case(tmp: Path, layout: float, pixel: float, *, strict: bool) -> tuple[int, dict]:
    source = tmp / "candidate.json"
    report = tmp / "report.json"
    source.write_text(json.dumps({
        "cases": [{
            "case_id": "case-01",
            "candidate": {
                "technical_status": "passed",
                "visual": {
                    "valid": True,
                    "metrics": {
                        "blurred_layout_ssim": layout,
                        "pixel_fidelity_score": pixel,
                    },
                },
            },
        }],
    }), encoding="utf-8")
    command = [sys.executable, str(SCRIPT), "--candidate-evaluation", str(source), "--report", str(report)]
    if strict:
        command.append("--strict")
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return result.returncode, json.loads(report.read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="visual-fidelity-gate-") as folder:
        tmp = Path(folder)
        rc, report = run_case(tmp, .30, .88, strict=True)
        assert rc != 0
        assert report["valid"] is False
        assert report["failed_count"] == 1
        codes = {item["code"] for item in report["cases"][0]["failures"]}
        assert "layout_similarity_below_policy" in codes
        assert "pixel_fidelity_below_policy" in codes

        rc, report = run_case(tmp, .97, .98, strict=True)
        assert rc == 0
        assert report["valid"] is True
        assert report["passed_count"] == 1
    print("12-case visual fidelity strict gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
