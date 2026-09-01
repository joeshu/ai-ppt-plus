#!/usr/bin/env python3
"""Regression test for the explicit approval-to-ingestion driver."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path, role: str) -> dict[str, str]:
    return {"role": role, "path": str(path), "sha256": digest(path)}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="approved-case-ingestion-") as temp:
        root = Path(temp)
        source = root / "reference.png"
        deck = root / "candidate.pptx"
        score = root / "score.json"
        report = root / "qa.json"
        source.write_bytes(b"reference-image")
        deck.write_bytes(b"editable-deck")
        score.write_text(json.dumps({"schema": "ai-ppt-plus/distillation-score/v1", "technical_valid": True, "blocker_count": 0, "weighted_score": 0.94, "metrics": {"pixel_fidelity": 0.94}}, ensure_ascii=False), encoding="utf-8")
        report.write_text(json.dumps({"schema": "ai-ppt-plus/editable-object-audit/v1", "valid": True}), encoding="utf-8")
        registry = root / "cases.json"
        registry.write_text(json.dumps({
            "schema": "ai-ppt-plus/distillation-case-registry/v1",
            "version": 1,
            "cases": [{
                "case_id": "case-1",
                "source_references": [ref(source, "source")],
                "candidates": [{"candidate_id": "candidate-1", "profile": "perfect-first", "status": "human-review-pending", "training_eligible": False, "deck": ref(deck, "candidate-deck"), "score": ref(score, "candidate-score"), "reports": [ref(report, "candidate-report")], "score_summary": {"weighted_score": 0.94, "metrics": {"pixel_fidelity": 0.94}}}],
                "learning_status": "human-review-pending",
            }],
        }, ensure_ascii=False), encoding="utf-8")
        output = root / "dataset.jsonl"
        manifest = root / "dataset-manifest.json"
        cycle_report = root / "cycle.json"
        index = root / "retrieval-index.json"
        evaluation = root / "retrieval-evaluation.json"
        ingest_report = root / "ingest.json"
        completed = subprocess.run([
            sys.executable, "scripts/ingest_approved_case.py",
            "--registry", str(registry), "--case-id", "case-1", "--candidate-id", "candidate-1",
            "--approved-by", "reviewer", "--approval-note", "visual text editability checked", "--human-confirmed",
            "--output", str(output), "--manifest", str(manifest), "--materialize-dir", str(root / "artifacts"),
            "--report", str(ingest_report), "--cycle-report", str(cycle_report), "--retrieval-index", str(index), "--retrieval-evaluation", str(evaluation),
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(ingest_report.read_text(encoding="utf-8"))
        assert result["status"] == "ingested" and result["human_confirmed"] is True
        cycle = json.loads(cycle_report.read_text(encoding="utf-8"))
        assert cycle["status"] == "prepared" and cycle["retrieval_ready"] is True
        retrieval = json.loads(index.read_text(encoding="utf-8"))
        assert retrieval["cpu_only"] is True and retrieval["trainable_weights"] is False
        assert len(output.read_text(encoding="utf-8").splitlines()) == 1
    print("approved case ingestion: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
