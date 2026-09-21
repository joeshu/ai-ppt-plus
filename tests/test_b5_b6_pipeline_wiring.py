#!/usr/bin/env python3
"""Exercise the B5 coordinate loop and B6 planner through the public DAG."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="b5-b6-pipeline-") as temp:
        root = Path(temp)
        project = root / "project"
        project.mkdir()
        layout = project / "layout.json"
        layout.write_text(json.dumps({
            "project_id": "b5-b6-pipeline-fixture",
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [{
                "texts": [{"object_id": "title", "text": "B5 B6 fixture", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "size": 18}],
                "tables": [{
                    "object_id": "fixture-table", "x": 0.1, "y": 0.45, "w": 0.8, "h": 0.25,
                    "columns": 2, "rows": [["渠道", "结果"], ["A", "通过"]],
                    "column_widths": [0.4, 0.4], "row_heights": [0.125, 0.125], "font_size_pt": 10,
                    "semantic_type": "native_table", "header_bold": True, "representation": "native",
                }],
            }],
        }), encoding="utf-8")
        deck = project / "deck.pptx"
        preview_dir = project / "preview"
        composed = subprocess.run(
            [sys.executable, "scripts/compose_pptx.py", str(layout), str(deck), "--preview-dir", str(preview_dir)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert composed.returncode == 0, composed.stdout + composed.stderr
        objects = project / "slide-object-manifest.json"
        built_objects = subprocess.run(
            [sys.executable, "scripts/build_object_manifest.py", str(layout), "--output", str(objects)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert built_objects.returncode == 0, built_objects.stdout + built_objects.stderr
        manifest = project / "slide-manifest.json"
        built_manifest = subprocess.run(
            [sys.executable, "scripts/build_slide_manifest.py", str(layout), "--object-manifest", str(objects), "--output", str(manifest)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert built_manifest.returncode == 0, built_manifest.stdout + built_manifest.stderr
        for name, value in (("handoff.json", {}), ("validation-report.json", {"status": "validated"}), ("issue-log.json", {"issues": []})):
            (project / name).write_text(json.dumps(value), encoding="utf-8")

        asset = project / "icon.png"
        image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        for x in range(20, 80):
            for y in range(20, 80):
                image.putpixel((x, y), (30, 110, 220, 255))
        image.save(asset)
        (project / "asset-render-records.json").write_text(json.dumps([{
            "schema": "ai-ppt-plus/asset-render-coordinate/v1",
            "page": 1,
            "object_id": "icon-1",
            "asset": {"path": "icon.png"},
            "slot": {"bbox_norm": [0.1, 0.1, 0.2, 0.2]},
            "render": {"canvas_px": [576, 324], "observed_visible_bbox_px": [105.48, 38.88, 124.92, 58.32]},
        }]), encoding="utf-8")
        (project / "authoring-plan.json").write_text(json.dumps({
            "schema": "ai-ppt-plus/authoring-plan/v1",
            "objects": [
                {"object_id": "icon-1", "page": 1, "semantic_role": "pictogram", "implementation_type": "imagegen_asset", "bbox": [0.1, 0.1, 0.2, 0.2], "protected_neighbors": ["footer"]},
                {"object_id": "footer", "page": 1, "semantic_role": "footer_system", "implementation_type": "native_shape", "bbox": [0.7, 0.1, 0.2, 0.2]},
            ],
        }), encoding="utf-8")
        before = project / "before"
        before.mkdir()
        preview_files = sorted(preview_dir.glob("*.png"))
        assert preview_files, list(preview_dir.iterdir())
        shutil.copy2(preview_files[0], before / "slide-1.png")

        run_dir = root / "run"
        command = [
            sys.executable, "scripts/run_pipeline.py", str(project), "--deck", str(deck),
            "--expected-pages", "1", "--execution-mode", "linear", "--output-dir", str(run_dir),
            "--asset-render-records", str(project / "asset-render-records.json"),
            "--require-asset-render-coordinate-loop",
            "--authoring-plan", str(project / "authoring-plan.json"),
            "--require-protected-repair-planner", "--protected-repair-decision", "accept",
            "--protected-repair-before-render-dir", str(before),
            "--require-coordinate-contract",
        ]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        data = json.loads(completed.stdout.strip().splitlines()[-1])
        assert data["valid"] is True and data["technical_valid"] is True
        coordinate = json.loads((run_dir / "coordinate-space-validation.json").read_text(encoding="utf-8"))
        table_layout = json.loads((run_dir / "table-layout-validation.json").read_text(encoding="utf-8"))
        assert coordinate["valid"] is True and coordinate["object_count"] >= 2
        assert table_layout["valid"] is True and table_layout["density_metrics"]
        report_index = json.loads((run_dir / "report-index.json").read_text(encoding="utf-8"))
        report_types = {entry["report_type"] for entry in report_index["reports"]}
        assert {"coordinate-space-validation", "table-layout-validation"} <= report_types
        coordinate = json.loads((run_dir / "asset-render-coordinate-report.json").read_text(encoding="utf-8"))
        assert coordinate["valid"] is True and coordinate["render_crop_evidence_count"] == 1
        repair = json.loads((run_dir / "protected-repair-plan.json").read_text(encoding="utf-8"))
        assert repair["valid"] is True and repair["status"] == "accepted" and repair["action_count"] == 1
        assert repair["evidence"]["captured"] is True
        pair = repair["actions"][0]["evidence"]["protected_neighbors"]["footer"]
        assert pair["material_regression"] is False
        assert Path(repair["actions"][0]["evidence"]["full_page"]["after"]["path"]).is_file()
    print("B5/B6 pipeline wiring: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
