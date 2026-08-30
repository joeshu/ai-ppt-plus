#!/usr/bin/env python3
"""Regression test for the project-manifest adapter."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="slide-manifest-") as tmp:
        root = Path(tmp)
        layout = root / "layout.json"
        objects = root / "slide-object-manifest.json"
        output = root / "slide-manifest.json"
        layout.write_text(json.dumps({"slides": [{"panels": [{"panel_id": "p1"}]}]}), encoding="utf-8")
        objects.write_text(json.dumps({
            "schema": "ai-ppt-plus/slide-object-manifest/v1",
            "project_id": "test-project",
            "slides": [{"slide_no": 1, "objects": [{
                "object_id": "title", "role": "formal-text", "object_type": "editable_text",
                "editability_level": "L1", "required_for_delivery": True,
                "human_review_required": False, "provenance": "layout.json",
            }]}],
        }), encoding="utf-8")
        result = run("scripts/build_slide_manifest.py", str(layout), "--object-manifest", str(objects), "--reference", "reference.png", "--formal-content-source", "outline.xlsx#row2", "--output", str(output))
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["slides"][0]["page_type"] == "infographic"
        assert data["slides"][0]["editability"]["counts_by_level"]["L1"] == 1
        check = run("scripts/validate_manifest.py", str(output), "--kind", "slide", "--require-editability")
        assert check.returncode == 0, check.stderr or check.stdout
    print("slide manifest builder: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
