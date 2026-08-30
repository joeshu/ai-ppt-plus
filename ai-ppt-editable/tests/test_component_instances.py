#!/usr/bin/env python3
"""Regression test for component instance validation and example rendering."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="component-instances-") as temp:
        report = Path(temp) / "validation.json"
        checked = subprocess.run([sys.executable, "scripts/validate_component_instances.py", "examples/component-library/standard-components.deck.json", "--components", "assets/component-library.template.json", "--layouts", "assets/layout-library.template.json", "--report", str(report)], cwd=ROOT, capture_output=True, text=True)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["usage"]["instances"] == 3 and data["usage"]["distinct_components"] == 3
        manifest = Path(temp) / "objects.json"
        built = subprocess.run([sys.executable, "scripts/build_object_manifest.py", "examples/component-library/standard-components.deck.json", "--output", str(manifest)], cwd=ROOT, capture_output=True, text=True)
        assert built.returncode == 0, built.stdout + built.stderr
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        assert manifest_data["component_usage"]["instances"] == 3
        manifest_report = Path(temp) / "object-validation.json"
        checked_manifest = subprocess.run([sys.executable, "scripts/validate_object_manifest.py", str(manifest), "--report", str(manifest_report)], cwd=ROOT, capture_output=True, text=True)
        assert checked_manifest.returncode == 0, checked_manifest.stdout + checked_manifest.stderr
        assert json.loads(manifest_report.read_text(encoding="utf-8"))["component_usage"]["distinct_components"] == 3
        deck = Path(temp) / "example.pptx"
        composed = subprocess.run([sys.executable, "scripts/compose_pptx.py", "examples/component-library/standard-components.deck.json", str(deck)], cwd=ROOT, capture_output=True, text=True)
        assert composed.returncode == 0, composed.stdout + composed.stderr
        rendered = subprocess.run([sys.executable, "scripts/render_pptx.py", str(deck), "--output-dir", str(Path(temp) / "render"), "--report", str(Path(temp) / "render.json")], cwd=ROOT, capture_output=True, text=True)
        assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    print("component instances and rendering: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
