#!/usr/bin/env python3
"""Regression tests for the automatic training-cycle driver."""
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_training_cycle.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, capture_output=True, text=True, check=False)


def ref(path: Path, role: str) -> dict[str, str]:
    return {"role": role, "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="training-cycle-") as temp:
        root = Path(temp)
        report = root / "cycle.json"
        skipped = run("--registry", str(root / "missing.json"), "--report", str(report))
        assert skipped.returncode == 0, skipped.stdout + skipped.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["status"] == "skipped" and data["code"] == "registry_not_found"

        registry = root / "cases.json"
        registry.write_text(json.dumps({"schema": "ai-ppt-plus/distillation-case-registry/v1", "version": 1, "cases": []}), encoding="utf-8")
        waiting = run("--registry", str(registry), "--report", str(report))
        assert waiting.returncode == 0, waiting.stdout + waiting.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["status"] == "waiting-human-approval" and data["retrieval_ready"] is False

        required = run("--registry", str(registry), "--report", str(report), "--require-approved")
        assert required.returncode == 2, required.stdout + required.stderr

        source = root / "source.png"
        deck = root / "candidate.pptx"
        score = root / "score.json"
        evidence = root / "report.json"
        source.write_bytes(b"source")
        deck.write_bytes(b"editable")
        score.write_text(json.dumps({"schema": "ai-ppt-plus/distillation-score/v1", "technical_valid": True, "blocker_count": 0}), encoding="utf-8")
        evidence.write_text(json.dumps({"schema": "ai-ppt-plus/dual-comparison/v1", "valid": True}), encoding="utf-8")
        registry.write_text(json.dumps({
            "schema": "ai-ppt-plus/distillation-case-registry/v1",
            "version": 1,
            "cases": [{
                "case_id": "approved-case",
                "source_references": [ref(source, "source")],
                "candidates": [{
                    "candidate_id": "approved-candidate",
                    "status": "human-approved",
                    "training_eligible": True,
                    "deck": ref(deck, "candidate-deck"),
                    "score": ref(score, "candidate-score"),
                    "reports": [ref(evidence, "report")],
                    "score_summary": {"weighted_score": 0.9, "metrics": {}},
                    "human_approval": {"schema": "ai-ppt-plus/distillation-human-approval/v1", "human_confirmed": True, "approved_by": "reviewer", "approval_note": "checked", "approved_at": "2026-09-01T00:00:00+00:00", "reviewed_dimensions": ["visual_fidelity", "formal_content", "editability"]},
                }],
            }],
        }), encoding="utf-8")
        output = root / "dataset.jsonl"
        manifest = root / "manifest.json"
        index = root / "index.json"
        evaluation = root / "evaluation.json"
        completed = run("--registry", str(registry), "--output", str(output), "--manifest", str(manifest), "--materialize-dir", str(root / "artifacts"), "--retrieval-index", str(index), "--retrieval-evaluation", str(evaluation), "--report", str(report))
        assert completed.returncode == 0, completed.stdout + completed.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["status"] == "prepared" and data["retrieval"]["status"] in {"passed", "insufficient-holdout"}
        assert index.is_file() and evaluation.is_file()

    print("automatic training cycle: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
