#!/usr/bin/env python3
"""Regression tests for explicit approval and hash-bound dataset export."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "training_export.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def ref(path: Path, role: str) -> dict:
    return {"role": role, "path": str(path), "sha256": digest(path)}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="training-export-") as temp:
        root = Path(temp)
        source = root / "source.png"
        deck = root / "candidate.pptx"
        source.write_bytes(b"source-image")
        deck.write_bytes(b"editable-pptx")
        score = write(root / "score.json", {"schema": "ai-ppt-plus/distillation-score/v1", "technical_valid": True, "blocker_count": 0, "weighted_score": 0.91, "metrics": {"visual_layout": 0.9, "pixel_fidelity": 0.9, "editability": 1.0, "technical": 1.0, "provenance": 1.0}})
        report = write(root / "report.json", {"schema": "ai-ppt-plus/dual-comparison/v1", "valid": True})
        registry = write(root / "registry.json", {"schema": "ai-ppt-plus/distillation-case-registry/v1", "version": 1, "cases": [{"case_id": "case-1", "source_references": [ref(source, "source")], "candidates": [{"candidate_id": "candidate-1", "profile": "hybrid", "status": "human-review-pending", "training_eligible": False, "deck": ref(deck, "candidate-deck"), "score": ref(score, "candidate-score"), "reports": [ref(report, "report")], "score_summary": {"weighted_score": 0.91, "metrics": {"editability": 1.0}, "technical_valid": True, "training_eligible": False}}], "learning_status": "human-review-pending"}]})
        approved = subprocess.run([sys.executable, str(SCRIPT), "approve-case", "--registry", str(registry), "--case-id", "case-1", "--candidate-id", "candidate-1", "--approved-by", "reviewer", "--approval-note", "visual, text, editability checked", "--human-confirmed"], capture_output=True, text=True, check=False)
        assert approved.returncode == 0, approved.stdout + approved.stderr
        data = json.loads(registry.read_text(encoding="utf-8"))
        candidate = data["cases"][0]["candidates"][0]
        assert candidate["training_eligible"] is True and candidate["human_approval"]["human_confirmed"] is True

        output = root / "dataset.jsonl"
        manifest_path = root / "dataset-manifest.json"
        exported = subprocess.run([sys.executable, str(SCRIPT), "export", "--registry", str(registry), "--output", str(output), "--manifest", str(manifest_path), "--materialize-dir", str(root / "artifacts")], capture_output=True, text=True, check=False)
        assert exported.returncode == 0, exported.stdout + exported.stderr
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        record = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
        assert manifest["retrieval_ready"] is True and manifest["supervised_training_ready"] is False
        assert manifest["record_count"] == 1 and manifest["rejected_count"] == 0
        assert record["provenance"]["human_approval"]["approved_by"] == "reviewer"
        assert all(item["path"].startswith("artifacts/") for item in record["source"])
    print("approved training export: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
