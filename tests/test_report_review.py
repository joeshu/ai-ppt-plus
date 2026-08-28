#!/usr/bin/env python3
"""Project aggregate and HTML review preserve technical/human/release states."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="report-review-") as temp:
        root = Path(temp)
        deck = root / "deck.pptx"
        deck.write_bytes(b"deck")
        child = root / "inspection.json"
        write(child, {"schema": "ai-ppt-plus/pptx-inspection/v1", "valid": True, "status": "passed", "deck_sha256": "deck-hash", "issues": []})
        index = root / "report-index.json"
        write(index, {"schema": "ai-ppt-plus/report-index/v1", "project_id": "demo", "revision": "R1", "stage": "validated", "validation_scope": "full", "deck_path": str(deck), "deck_sha256": "deck-hash", "source_references": [], "reports": [{"report_type": "inspection", "path": child.name, "required": True, "stage": "validated"}]})
        aggregate = root / "project-report.json"
        result = subprocess.run([sys.executable, "scripts/aggregate_project_reports.py", str(index), "--report", str(aggregate)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(aggregate.read_text(encoding="utf-8"))
        assert report["technical_valid"] is True and report["release_eligible"] is False and report["human_review_status"] == "pending" and report["validation_scope"] == "full"
        evidence = report["evidence"]["reports"][0]
        assert {"technical_valid", "human_review_required", "release_eligible", "source"} <= set(evidence)

        run_dir = root / "run"
        run_dir.mkdir()
        rendered = run_dir / "rendered"
        rendered.mkdir()
        from PIL import Image
        Image.new("RGB", (320, 180), "#18324f").save(rendered / "slide-1.png")
        pipeline = run_dir / "pipeline-result.json"
        write(pipeline, {"schema": "ai-ppt-plus/pipeline-run/v2", "valid": True, "status": "passed", "technical_valid": True, "technical_status": "passed", "validation_scope": "incremental", "full_deck_validation_required": True, "release_eligible": False, "release_status": "not_run", "human_review_required": True, "human_review_status": "pending", "run_id": "run-1", "project": "demo", "deck": str(deck), "deck_sha256": "deck-hash", "source_references": [], "run_dir": str(run_dir), "execution": {"mode": "dag", "affected_pages": [1], "affected_regions": ["title=0,0,100,40"]}, "steps": [{"name": "render", "ok": True, "duration_ms": 4.2, "cache_hit": False, "deps": [], "stdout": str(run_dir / "render.stdout.txt"), "stderr": str(run_dir / "render.stderr.txt")}], "failed_steps": [], "technical_failed_steps": [], "next_state": "validated", "human_visual_review_required": True, "human_signoff_required": True, "quality_evidence": {}})
        (run_dir / "render.stdout.txt").write_text("ok", encoding="utf-8")
        (run_dir / "render.stderr.txt").write_text("", encoding="utf-8")
        html_path = run_dir / "review.html"
        generated = subprocess.run([sys.executable, "scripts/render_review_html.py", str(pipeline), "--output", str(html_path)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert generated.returncode == 0, generated.stdout + generated.stderr
        html = html_path.read_text(encoding="utf-8")
        assert "技术通过" in html and "人工待审" in html and "未放行" in html and "slide-1.png" in html
    print("report envelope and HTML review: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
