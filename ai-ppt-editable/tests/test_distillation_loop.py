#!/usr/bin/env python3
"""Regression tests for score, feedback, gate, and case registry behavior."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "distillation_loop.py"


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="distillation-loop-") as temp:
        root = Path(temp)
        report = write(root / "dual.json", {
            "schema": "ai-ppt-plus/dual-comparison/v1",
            "valid": True,
            "pixel_comparison": {"hash_bound": True, "aggregate": {"mean_blurred_layout_ssim": 0.94, "mean_pixel_fidelity_score": 0.91}},
            "object_comparison": {"valid": True, "expected_objects": 10, "audited_objects": 10},
            "issues": [{"severity": "minor", "code": "font_missing_warning", "message": "font fallback observed"}],
        })
        score = root / "score.json"
        checked = subprocess.run([
            sys.executable, str(SCRIPT), "score", "--candidate-id", "c1", "--profile", "hybrid",
            "--report", str(report), "--output", str(score),
        ], capture_output=True, text=True, check=False)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(score.read_text(encoding="utf-8"))
        assert data["technical_valid"] is True, data
        assert data["metrics"]["editability"] == 1.0, data
        assert data["feedback"][0]["owner"] == "font", data

        baseline = write(root / "baseline.json", {"weighted_score": 0.96, "metrics": {"visual_layout": 0.96, "pixel_fidelity": 0.95, "editability": 1.0, "technical": 1.0, "provenance": 1.0}})
        gate = root / "gate.json"
        checked = subprocess.run([
            sys.executable, str(SCRIPT), "gate", "--candidate-score", str(score), "--baseline-score", str(baseline), "--output", str(gate),
        ], capture_output=True, text=True, check=False)
        assert checked.returncode == 2
        gate_data = json.loads(gate.read_text(encoding="utf-8"))
        assert gate_data["decision"] == "reject-and-rollback", gate_data
        assert gate_data["rollback_action"] == "keep_previous_candidate", gate_data

        deck = root / "candidate.pptx"
        deck.write_bytes(b"pptx-fixture")
        registry = root / "registry.json"
        checked = subprocess.run([
            sys.executable, str(SCRIPT), "record-case", "--registry", str(registry), "--case-id", "case-1",
            "--candidate-id", "c1", "--source", str(report), "--deck", str(deck), "--score", str(score), "--report", str(report),
        ], capture_output=True, text=True, check=False)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        registry_data = json.loads(registry.read_text(encoding="utf-8"))
        assert registry_data["schema"] == "ai-ppt-plus/distillation-case-registry/v1"
        assert len(registry_data["cases"]) == 1
        assert registry_data["cases"][0]["candidates"][0]["deck"]["sha256"]
    print("automatic distillation loop: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
