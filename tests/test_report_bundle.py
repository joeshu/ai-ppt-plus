#!/usr/bin/env python3
"""Report bundle freshness gate catches stale and inconsistent evidence."""
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


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run_gate(root: Path, pipeline: Path, index: Path, aggregate: Path, output: Path, *, review: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "scripts/validate_report_bundle.py",
        str(pipeline),
        "--report-index",
        str(index),
        "--project-report",
        str(aggregate),
        "--deck",
        str(root / "deck.pptx"),
        "--report",
        str(output),
    ]
    if review:
        command.extend(["--review-html", str(review)])
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="report-bundle-") as temp:
        root = Path(temp)
        deck = root / "deck.pptx"
        deck.write_bytes(b"deterministic deck")
        deck_hash = digest(deck)
        child = root / "inspection.json"
        write(child, {"schema": "ai-ppt-plus/pptx-inspection/v1", "valid": True, "status": "passed", "issues": []})
        index = root / "report-index.json"
        write(index, {
            "schema": "ai-ppt-plus/report-index/v1",
            "project_id": "bundle-fixture",
            "revision": "R1",
            "stage": "validated",
            "validation_scope": "full",
            "deck_path": str(deck),
            "deck_sha256": deck_hash,
            "source_references": [{"source_id": "deck", "path": str(deck), "sha256": deck_hash}],
            "reports": [{"report_type": "inspection", "path": child.name, "required": True, "stage": "validated", "step_ok": True}],
        })
        aggregate = root / "project-report.json"
        aggregated = subprocess.run([sys.executable, "scripts/aggregate_project_reports.py", str(index), "--report", str(aggregate)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert aggregated.returncode == 0, aggregated.stdout + aggregated.stderr

        run_dir = root / "run"
        run_dir.mkdir()
        pipeline = run_dir / "pipeline-result.json"
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
            "human_review_required": True,
            "human_review_status": "pending",
            "run_id": "run-bundle",
            "project": str(root),
            "deck": str(deck),
            "deck_sha256": deck_hash,
            "source_references": [{"source_id": "deck", "path": str(deck), "sha256": deck_hash}],
            "run_dir": str(run_dir),
            "steps": [{"name": "inspection", "ok": True}, {"name": "project-report-aggregate", "ok": True}],
            "failed_steps": [],
            "technical_failed_steps": [],
            "next_state": "validated",
            "human_visual_review_required": True,
            "human_signoff_required": True,
            "execution": {"mode": "dag", "affected_pages": "all", "affected_regions": []},
        })
        review = run_dir / "review.html"
        review.write_text("技术通过 人工待审 未放行", encoding="utf-8")
        bundle = run_dir / "report-bundle-validation.json"
        result = run_gate(root, pipeline, index, aggregate, bundle, review=review)
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(bundle.read_text(encoding="utf-8"))
        assert report["valid"] is True and report["status"] == "passed"
        schema = json.loads((ROOT / "assets/schemas/report-bundle-validation.schema.json").read_text(encoding="utf-8"))
        sys.path.insert(0, str(ROOT / "scripts"))
        from schema_contract import validate  # noqa: E402
        assert not validate(report, schema)

        child.write_text(child.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        stale_child = run_gate(root, pipeline, index, aggregate, root / "stale-child.json")
        assert stale_child.returncode == 2
        stale_child_report = json.loads((root / "stale-child.json").read_text(encoding="utf-8"))
        assert any(issue["code"] in {"child_hash_fresh", "child_input_hash_fresh", "child_source_hash_fresh"} for issue in stale_child_report["issues"])

        aggregate_data = json.loads(aggregate.read_text(encoding="utf-8"))
        aggregate_data["report_index_sha256"] = "0" * 64
        write(aggregate, aggregate_data)
        stale_index = run_gate(root, pipeline, index, aggregate, root / "stale-index.json")
        assert stale_index.returncode == 2
        stale_index_report = json.loads((root / "stale-index.json").read_text(encoding="utf-8"))
        assert any(issue["code"] == "report_index_hash_fresh" for issue in stale_index_report["issues"])

        pipeline_data = json.loads(pipeline.read_text(encoding="utf-8"))
        pipeline_data["validation_scope"] = "incremental"
        pipeline_data["full_deck_validation_required"] = True
        pipeline_data["execution"]["affected_pages"] = [1]
        write(pipeline, pipeline_data)
        inconsistent = run_gate(root, pipeline, index, aggregate, root / "inconsistent.json")
        assert inconsistent.returncode == 2
        inconsistent_report = json.loads((root / "inconsistent.json").read_text(encoding="utf-8"))
        assert any(issue["code"] == "validation_scope_consistent" for issue in inconsistent_report["issues"])
    print("report bundle freshness and consistency: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
