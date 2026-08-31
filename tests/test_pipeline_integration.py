#!/usr/bin/env python3
"""Exercise the public pipeline entrypoint in DAG and incremental modes."""
from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from schema_contract import validate  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pipeline-integration-") as temp:
        root = Path(temp)
        project = root / "project"
        project.mkdir()
        layout = project / "layout.json"
        layout.write_text(json.dumps({
            "project_id": "pipeline-fixture",
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [{"texts": [{"object_id": "title", "text": "DAG fixture", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "size": 18}]}],
        }), encoding="utf-8")
        deck = project / "deck.pptx"
        preview_dir = project / "preview"
        composed = subprocess.run([sys.executable, "scripts/compose_pptx.py", str(layout), str(deck), "--preview-dir", str(preview_dir)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert composed.returncode == 0, composed.stdout + composed.stderr
        objects = project / "slide-object-manifest.json"
        built_objects = subprocess.run([sys.executable, "scripts/build_object_manifest.py", str(layout), "--output", str(objects)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert built_objects.returncode == 0, built_objects.stdout + built_objects.stderr
        manifest = project / "slide-manifest.json"
        built_manifest = subprocess.run([sys.executable, "scripts/build_slide_manifest.py", str(layout), "--object-manifest", str(objects), "--output", str(manifest)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert built_manifest.returncode == 0, built_manifest.stdout + built_manifest.stderr
        for name, value in (("handoff.json", {}), ("validation-report.json", {"status": "validated"}), ("issue-log.json", {"issues": []})):
            (project / name).write_text(json.dumps(value), encoding="utf-8")
        cache = root / "cache"
        runs = []
        for number in (1, 2):
            run_dir = root / f"run-{number}"
            command = [sys.executable, "scripts/run_pipeline.py", str(project), "--deck", str(deck), "--expected-pages", "1", "--affected-pages", "1", "--affected-region", "title=0,0,100,40", "--preview-dir", str(preview_dir), "--require-preview-consistency", "--execution-mode", "dag", "--cache-dir", str(cache), "--output-dir", str(run_dir)]
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            assert completed.returncode == 0, completed.stdout + completed.stderr
            data = json.loads(completed.stdout.strip().splitlines()[-1])
            assert data["valid"] is True and data["technical_valid"] is True and data["execution"]["affected_pages"] == [1]
            assert data["execution"]["page_cache"]["enabled"] is True
            assert data["execution"]["duration_ms"] >= 0
            assert data["execution"]["critical_path_ms"] >= 0
            assert data["execution"]["cache_misses"] >= 0
            assert data["performance_report"] == str((run_dir / "performance-report.json").resolve())
            performance = json.loads((run_dir / "performance-report.json").read_text(encoding="utf-8"))
            assert performance["schema"] == "ai-ppt-plus/performance-report/v1"
            assert performance["execution"]["cache_hit_rate"] is not None
            assert data["source_references"]
            assert not validate(data, json.loads((ROOT / "assets/schemas/pipeline-run.schema.json").read_text(encoding="utf-8")))
            assert not validate(json.loads((run_dir / "report-index.json").read_text(encoding="utf-8")), json.loads((ROOT / "assets/schemas/report-index.schema.json").read_text(encoding="utf-8")))
            assert (run_dir / "review.html").is_file()
            bundle = json.loads((run_dir / "report-bundle-validation.json").read_text(encoding="utf-8"))
            assert bundle["valid"] is True and bundle["status"] == "passed"
            assert data["quality_evidence"]["report_bundle_preflight"]["valid"] is True
            semantic = json.loads((run_dir / "semantic-object-audit.json").read_text(encoding="utf-8"))
            assert semantic["valid"] is True
            assert data["quality_evidence"]["semantic_object_audit"]["valid"] is True
            assert data["quality_evidence"]["preview_consistency"]["valid"] is True
            assert data["finalization"]["report_bundle"]["status"] == "passed"
            runs.append(data)
        assert runs[1]["execution"]["cache_hits"] > 0, runs[1]["execution"]
        gate = json.loads((Path(runs[1]["run_dir"]) / "render-visual-gate.json").read_text(encoding="utf-8"))
        assert gate["selected_pages"] == [1] and gate["valid"] is True
        reference_dir = root / "reference-deck"
        reference_dir.mkdir()
        shutil.copy2(Path(runs[0]["run_dir"]) / "rendered" / "slide-1.png", reference_dir / "slide-1.png")
        dual_run = root / "run-dual"
        dual_command = [
            sys.executable,
            "scripts/run_pipeline.py",
            str(project),
            "--deck", str(deck),
            "--expected-pages", "1",
            "--affected-pages", "1",
            "--preview-dir", str(preview_dir),
            "--require-preview-consistency",
            "--reference-dir", str(reference_dir),
            "--object-manifest", str(objects),
            "--require-dual-comparison",
            "--review-package-dir", str(dual_run / "review-package"),
            "--execution-mode", "dag",
            "--cache-dir", str(cache),
            "--output-dir", str(dual_run),
        ]
        dual_completed = subprocess.run(dual_command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert dual_completed.returncode == 0, dual_completed.stdout + dual_completed.stderr
        dual_data = json.loads(dual_completed.stdout.strip().splitlines()[-1])
        dual_report = json.loads((dual_run / "dual-comparison.json").read_text(encoding="utf-8"))
        assert dual_report["valid"] is True and dual_report["status"] == "passed"
        assert dual_report["pixel_comparison"]["valid"] is True
        assert dual_report["object_comparison"]["valid"] is True
        assert dual_data["quality_evidence"]["dual_comparison"]["valid"] is True
        assert (dual_run / "review-package" / "artifacts" / "performance-report.json").is_file()
        assert (dual_run / "review-package" / "artifacts" / "dual-comparison.json").is_file()
        persisted = json.loads((dual_run / "pipeline-result.json").read_text(encoding="utf-8"))
        assert persisted["review_package"]["valid"] is True and persisted["review_package"]["status"] == "passed"
        assert persisted["review_package"] == dual_data["review_package"]
        package_manifest = json.loads((dual_run / "review-package/review-package.json").read_text(encoding="utf-8"))
        pipeline_hash = hashlib.sha256((dual_run / "pipeline-result.json").read_bytes()).hexdigest()
        assert package_manifest["pipeline_result_sha256"] == pipeline_hash
        copied_pipeline = dual_run / "review-package/artifacts/pipeline-result.json"
        assert copied_pipeline.is_file() and hashlib.sha256(copied_pipeline.read_bytes()).hexdigest() == pipeline_hash
        final_bundle = json.loads((dual_run / "report-bundle-validation.json").read_text(encoding="utf-8"))
        assert final_bundle["pipeline_result_sha256"] == pipeline_hash
    print("pipeline DAG integration and incremental page mode: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
