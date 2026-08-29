#!/usr/bin/env python3
"""Regression tests for independent visible-content and backend gates."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="content-inventory-") as temp:
        root = Path(temp)
        layout = root / "layout.json"
        write(layout, {"slide_width_in": 4, "slide_height_in": 2.25, "slides": [{"texts": [
            {"object_id": "title", "text": "可见标题", "x": 0.1, "y": 0.1, "w": 0.6, "h": 0.2, "size": 18},
            {"object_id": "month-01", "text": "1月", "x": 0.1, "y": 0.5, "w": 0.2, "h": 0.2, "size": 10},
            {"object_id": "value-01", "text": "20.0", "x": 0.3, "y": 0.5, "w": 0.2, "h": 0.2, "size": 10},
        ]}]})
        deck = root / "deck.pptx"
        composed = run("scripts/compose_pptx.py", str(layout), str(deck))
        assert composed.returncode == 0, composed.stdout + composed.stderr

        objects = root / "slide-object-manifest.json"
        write(objects, {"slides": [{"slide_no": 1, "objects": [
            {"object_id": "title", "object_type": "editable_text", "text_spec": {"content": "可见标题"}},
            {"object_id": "month-01", "object_type": "editable_text", "text_spec": {"content": "1月"}},
            {"object_id": "value-01", "object_type": "editable_text", "text_spec": {"content": "20.0"}},
        ]}]})
        text_manifest = root / "text-layout-manifest.json"
        write(text_manifest, {"slides": [{"slide_no": 1, "text_specs": [
            {"text_id": "title", "content": "可见标题"},
            {"text_id": "month-01", "content": "1月"},
            {"text_id": "value-01", "content": "20.0"},
        ]}]})
        inventory = root / "content-inventory.json"
        write(inventory, {"schema": "ai-ppt-plus/content-inventory/v1", "project_id": "fixture", "authority": "user_transcription", "slides": [{
            "slide_no": 1,
            "visible_text": [{"object_id": "title", "content": "可见标题"}],
            "charts": [{
                "chart_id": "chart-01", "representation": "static_line_primitives", "source_data_status": "unavailable",
                "required_elements": ["category_labels", "data_labels"],
                "visible_elements": {
                    "category_labels": [{"object_id": "month-01", "content": "1月"}],
                    "data_labels": [{"object_id": "value-01", "content": "20.0"}],
                },
            }],
            "required_object_ids": ["title", "month-01", "value-01"],
        }]})
        report = root / "content-report.json"
        checked = run("scripts/validate_content_inventory.py", str(inventory), "--object-manifest", str(objects), "--text-manifest", str(text_manifest), "--deck", str(deck), "--expected-pages", "1", "--report", str(report))
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True and data["chart_annotation_count"] == 2, data

        bad = json.loads(inventory.read_text(encoding="utf-8"))
        bad["slides"][0]["charts"][0]["visible_elements"]["data_labels"] = []
        write(inventory, bad)
        failed = run("scripts/validate_content_inventory.py", str(inventory), "--expected-pages", "1")
        assert failed.returncode == 2 and "chart_visible_element_missing" in failed.stdout, failed.stdout

        environment = root / "environment.json"
        env_check = run("scripts/probe_environment.py", "--output", str(environment))
        assert env_check.returncode == 0, env_check.stdout + env_check.stderr
        binding = run("scripts/validate_backend_binding.py", str(environment), str(ROOT / "assets/skill-routing.template.json"), "--skill-dir", str(ROOT))
        assert binding.returncode == 0, binding.stdout + binding.stderr
    print("content inventory and backend binding: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
