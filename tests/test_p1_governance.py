#!/usr/bin/env python3
"""Regression coverage for P1 reliability and review contracts."""
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, script, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="p1-governance-") as temp:
        root = Path(temp)
        design = root / "design-system.yaml"
        design.write_text((ROOT / "assets/design-system.template.yaml").read_text(encoding="utf-8").replace("approval_status: draft", "approval_status: approved"), encoding="utf-8")
        design_check = run("scripts/validate_design_system.py", str(design), "--strict")
        assert design_check.returncode == 0, design_check.stdout + design_check.stderr
        issue_log = root / "issue-log.json"
        write_json(issue_log, {"schema": "ai-ppt-plus/issue-log/v1", "project_id": "p1", "revision": "R1", "issues": [{"id": "P1-001", "severity": "major", "status": "closed", "owner": "root", "trigger": "cache corruption", "root_cause": "unverified artifact", "fix": "hash and quarantine", "regression_test": "tests/test_pipeline_engine.py", "affected_stages": ["cache"], "resolved_revision": "R1"}]})
        issue_check = run("scripts/validate_issue_log.py", str(issue_log), "--strict")
        assert issue_check.returncode == 0, issue_check.stdout + issue_check.stderr
        open_log = json.loads(issue_log.read_text(encoding="utf-8")); open_log["issues"][0]["status"] = "open"; write_json(issue_log, open_log)
        issue_blocked = run("scripts/validate_issue_log.py", str(issue_log), "--strict")
        assert issue_blocked.returncode == 2 and "open_issues_block_strict" in issue_blocked.stdout, issue_blocked.stdout

        pipeline_result = root / "pipeline-result.json"
        write_json(pipeline_result, {"project": "p1", "run_id": "run-1", "run_dir": str(root), "technical_status": "passed", "human_review_status": "pending", "release_status": "blocked", "technical_valid": True, "release_eligible": False, "validation_scope": "full", "failed_steps": [], "steps": [{"name": "source", "deps": [], "duration_ms": 100}, {"name": "render", "deps": ["source"], "duration_ms": 300}, {"name": "qa", "deps": ["source"], "duration_ms": 50}], "execution": {"mode": "dag", "affected_pages": "all", "affected_regions": []}})
        review = run("scripts/build_review_package.py", str(pipeline_result), "--output", str(root / "review-package"))
        assert review.returncode == 0, review.stdout + review.stderr
        package = json.loads((root / "review-package/review-package.json").read_text(encoding="utf-8"))
        assert package["schema"] == "ai-ppt-plus/review-package/v1" and package["artifact_count"] >= 2
        stale = root / "review-package/artifacts/rendered/slide-99.png"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(b"stale")
        review = run("scripts/build_review_package.py", str(pipeline_result), "--output", str(root / "review-package"))
        assert review.returncode == 0 and not stale.exists(), review.stdout + review.stderr

        performance = root / "performance-report.json"
        perf = run("scripts/build_performance_report.py", str(pipeline_result), "--output", str(performance), "--issue-log", str(issue_log), "--repair-round", "2")
        assert perf.returncode == 0, perf.stdout + perf.stderr
        performance_data = json.loads(performance.read_text(encoding="utf-8"))
        assert performance_data["schema"] == "ai-ppt-plus/performance-report/v1"
        assert performance_data["execution"]["repair_rounds"] == 2
        assert performance_data["execution"]["critical_path_ms"] == 400

        rendered = root / "rendered.png"; rendered.write_bytes(b"rendered")
        reference = root / "reference.png"; reference.write_bytes(b"reference")
        visual_report = root / "visual-comparison.json"
        write_json(visual_report, {"schema": "ai-ppt-plus/visual-comparison/v1", "valid": True, "pages": [{"slide": 1, "rendered": str(rendered), "rendered_sha256": hashlib.sha256(rendered.read_bytes()).hexdigest(), "reference": str(reference), "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest()}], "aggregate": {}})
        object_manifest = root / "slide-object-manifest.json"
        write_json(object_manifest, {"slides": [{"slide_no": 1, "objects": [{"object_id": "title", "object_type": "editable_text"}]}]})
        deck = root / "deck.pptx"; deck.write_bytes(b"deck")
        object_report = root / "semantic-object-audit.json"
        write_json(object_report, {"valid": True, "deck_sha256": hashlib.sha256(deck.read_bytes()).hexdigest(), "object_manifest_sha256": hashlib.sha256(object_manifest.read_bytes()).hexdigest(), "expected_object_count": 1, "audited_object_count": 1, "observed_top_level_shape_count": 1, "undeclared_shape_count": 0, "errors": [], "warnings": []})
        dual_report = root / "dual-comparison.json"
        dual = run("scripts/compare_dual.py", "--visual-report", str(visual_report), "--object-report", str(object_report), "--object-manifest", str(object_manifest), "--deck", str(deck), "--report", str(dual_report), "--require-object")
        assert dual.returncode == 0, dual.stdout + dual.stderr
        dual_data = json.loads(dual_report.read_text(encoding="utf-8"))
        assert dual_data["schema"] == "ai-ppt-plus/dual-comparison/v1"
        assert dual_data["pixel_comparison"]["valid"] is True and dual_data["object_comparison"]["valid"] is True
        assert dual_data["pixel_comparison"]["hash_bound"] is True
        assert dual_data["pixel_comparison"]["compared_pages"] == 1

        single_visual_report = root / "single-visual-comparison.json"
        write_json(single_visual_report, {"schema": "ai-ppt-plus/visual-comparison/v1", "valid": True, "rendered": str(rendered), "rendered_sha256": hashlib.sha256(rendered.read_bytes()).hexdigest(), "reference": str(reference), "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(), "metrics": {"blurred_layout_ssim": 0.9, "pixel_fidelity_score": 0.8}})
        single_dual_report = root / "single-dual-comparison.json"
        single_dual = run("scripts/compare_dual.py", "--visual-report", str(single_visual_report), "--object-report", str(object_report), "--object-manifest", str(object_manifest), "--deck", str(deck), "--report", str(single_dual_report), "--require-object")
        assert single_dual.returncode == 0, single_dual.stdout + single_dual.stderr
        single_data = json.loads(single_dual_report.read_text(encoding="utf-8"))
        assert single_data["pixel_comparison"]["compared_pages"] == 1
        assert single_data["pixel_comparison"]["aggregate"]["mean_pixel_fidelity_score"] == 0.8
        assert single_data["pixel_comparison"]["metrics"]["blurred_layout_ssim"] == 0.9
        stale_object = json.loads(object_report.read_text(encoding="utf-8")); stale_object["deck_sha256"] = "0" * 64; write_json(object_report, stale_object)
        blocked = run("scripts/compare_dual.py", "--visual-report", str(visual_report), "--object-report", str(object_report), "--object-manifest", str(object_manifest), "--deck", str(deck), "--report", str(dual_report), "--require-object")
        assert blocked.returncode == 2 and "object_comparison_stale_deck" in blocked.stdout, blocked.stdout
        print("root P1 governance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
