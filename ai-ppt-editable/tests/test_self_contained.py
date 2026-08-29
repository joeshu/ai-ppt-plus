#!/usr/bin/env python3
"""Smoke-test the standalone editable skill package and native composition."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    package = run("scripts/validate_skill_package.py", "--skill-dir", str(ROOT))
    assert package.returncode == 0, package.stdout + package.stderr
    routing = run("scripts/validate_routing_contract.py")
    assert routing.returncode == 0, routing.stdout + routing.stderr
    assert (ROOT / "assets" / "fonts" / "NotoSansSC-Regular.ttf").stat().st_size > 1_000_000
    with tempfile.TemporaryDirectory(prefix="editable-self-contained-") as temp:
        root = Path(temp)
        layout = root / "layout.json"
        layout.write_text(json.dumps({
            "project_id": "standalone-smoke",
            "slide_width_in": 13.333333,
            "slide_height_in": 7.5,
            "slides": [{
                "background_color": "F7F8FA",
                "texts": [{"object_id": "title", "text": "可编辑技能独立运行", "x": 0.8, "y": 0.8, "w": 6.0, "h": 0.8, "size": 28}],
            }],
        }, ensure_ascii=False), encoding="utf-8")
        output = root / "editable.pptx"
        composed = run("scripts/compose_pptx.py", str(layout), str(output))
        assert composed.returncode == 0, composed.stdout + composed.stderr
        with zipfile.ZipFile(output) as archive:
            slide = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        assert "可编辑技能独立运行" in slide
    print("editable self-contained smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
