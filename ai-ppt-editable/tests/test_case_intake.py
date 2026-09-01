#!/usr/bin/env python3
"""Regression tests for operator-only image/PPTX case intake."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_case.py"


def run(*args: str) -> dict:
    completed = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="case-intake-") as temp:
        root = Path(temp)
        image = root / "页 1.png"
        image.write_bytes(b"minimal image fixture")
        first = run("--source", str(image), "--output-dir", str(root / "cases"), "--case-id", "image-case")
        intake = json.loads(Path(first["intake_path"]).read_text(encoding="utf-8"))
        assert intake["input_mode"] == "image"
        assert intake["training_eligible"] is False
        registry = json.loads(Path(first["registry_path"]).read_text(encoding="utf-8"))
        assert registry["cases"][0]["learning_status"] == "human-review-pending"
        assert registry["cases"][0]["candidates"][0]["status"] == "awaiting-reconstruction"

        pptx = root / "target.pptx"
        pptx.write_bytes(b"minimal pptx fixture")
        second = run("--source", str(pptx), "--output-dir", str(root / "cases"), "--case-id", "pptx-case", "--skip-render")
        pptx_intake = json.loads(Path(second["intake_path"]).read_text(encoding="utf-8"))
        assert pptx_intake["input_mode"] == "pptx"
        assert pptx_intake["canonical_target_references"]
        assert pptx_intake["render_status"][0]["status"] == "skipped"

        candidate = root / "candidate.pptx"
        candidate.write_bytes(b"candidate-pptx")
        score = root / "score.json"
        score.write_text(json.dumps({"schema": "ai-ppt-plus/distillation-score/v1", "weighted_score": 0.93, "technical_valid": True, "blocker_count": 0, "metrics": {"pixel_fidelity": 0.92}}, ensure_ascii=False), encoding="utf-8")
        qa = root / "qa.json"
        qa.write_text(json.dumps({"schema": "ai-ppt-plus/editable-object-audit/v1", "valid": True}), encoding="utf-8")
        third = run("--source", str(image), "--output-dir", str(root / "cases"), "--case-id", "evidence-case", "--candidate", str(candidate), "--candidate-score", str(score), "--candidate-report", str(qa), "--profile", "perfect-first")
        evidence_candidate = json.loads(Path(third["intake_path"]).read_text(encoding="utf-8"))["case_id"]
        assert evidence_candidate == "evidence-case"
        evidence_registry = json.loads(Path(third["registry_path"]).read_text(encoding="utf-8"))
        record = evidence_registry["cases"][-1]["candidates"][0]
        assert record["status"] == "awaiting-human-approval"
        assert record["evidence_status"] == "attached"
        assert record["score_summary"]["weighted_score"] == 0.93
        assert len(record["reports"]) == 1
        assert all((root / "cases" / ref["path"]).is_file() for ref in [record["deck"], record["score"], *record["reports"]])
    print("case intake: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
