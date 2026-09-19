#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="short-loop-state-") as temp:
        root = Path(temp)
        deck = root / "deck.pptx"
        deck.write_bytes(b"short-loop-deck")
        deck_hash = sha(deck)

        visual = root / "visual-comparison.json"
        write(visual, {
            "schema": "ai-ppt-plus/reference-visual/v1",
            "valid": False,
            "status": "failed",
            "metrics": {"reference_fidelity_score": 0.31, "blurred_layout_ssim": 0.42},
            "issues": [{"code": "visual_mismatch"}],
        })

        index = root / "report-index.json"
        write(index, {
            "schema": "ai-ppt-plus/report-index/v1",
            "project_id": "short-loop-state",
            "revision": "R1",
            "stage": "repair-required",
            "validation_scope": "full",
            "deck_path": str(deck),
            "deck_sha256": deck_hash,
            "source_references": [{"source_id": "deck", "path": str(deck), "sha256": deck_hash}],
            "reports": [{
                "report_type": "visual-comparison",
                "path": visual.name,
                "required": True,
                "stage": "validated",
                "step_ok": False,
            }],
        })

        aggregate = root / "project-report.json"
        result = subprocess.run(
            [sys.executable, "scripts/aggregate_project_reports.py", str(index), "--report", str(aggregate)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        project = json.loads(aggregate.read_text(encoding="utf-8"))
        assert project["valid"] is True
        assert project["technical_valid"] is True
        assert project["repair_loop_required"] is True
        assert project["production_state"] == "repair-required"
        assert project["next_state"] == "repair-required"
        assert any(item["code"] == "visual_diagnostic_requires_repair" for item in project["repair_signals"])
        assert not any(item.get("severity") == "blocker" for item in project["issues"])

        pipeline = root / "pipeline-result.json"
        write(pipeline, {
            "schema": "ai-ppt-plus/pipeline-run/v2",
            "valid": True,
            "status": "passed",
            "technical_valid": True,
            "technical_status": "passed",
            "validation_scope": "full",
            "full_deck_validation_required": False,
            "release_eligible": False,
            "release_status": "not_run",
            "repair_loop_required": True,
            "repair_signals": [{"evidence": "visual_comparison", "diagnostic_only": True}],
            "production_state": "repair-required",
            "human_review_required": True,
            "human_review_status": "pending",
            "run_id": "run-short-loop",
            "project": str(root),
            "deck": str(deck),
            "deck_sha256": deck_hash,
            "source_references": [{"source_id": "deck", "path": str(deck), "sha256": deck_hash}],
            "run_dir": str(root),
            "steps": [
                {"name": "visual-comparison", "ok": False},
                {"name": "project-report-aggregate", "ok": True},
            ],
            "failed_steps": ["visual-comparison"],
            "technical_failed_steps": [],
            "next_state": "repair-required",
            "human_visual_review_required": True,
            "human_signoff_required": True,
            "execution": {"mode": "dag", "affected_pages": "all", "affected_regions": []},
        })

        bundle = root / "report-bundle-validation.json"
        bundled = subprocess.run(
            [
                sys.executable,
                "scripts/validate_report_bundle.py",
                str(pipeline),
                "--report-index", str(index),
                "--project-report", str(aggregate),
                "--deck", str(deck),
                "--report", str(bundle),
            ],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert bundled.returncode == 0, bundled.stdout + bundled.stderr
        report = json.loads(bundle.read_text(encoding="utf-8"))
        assert report["valid"] is True
        assert report["technical_valid"] is True
        assert report["repair_loop_required"] is True
        assert report["production_state"] == "repair-required"

    print("short-loop report state: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
