#!/usr/bin/env python3
"""Regression test for manifests that use a separate assets directory."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def run(*args: str):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="object-manifest-paths-") as temp:
        root = Path(temp)
        assets = root / "assets"
        assets.mkdir()
        for name in ("background.png", "logo.png"):
            (assets / name).write_bytes(PNG_1X1)
        layout = root / "layout.json"
        layout.write_text(json.dumps({
            "project_id": "asset-path-fixture",
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "assets_dir": str(assets),
            "slides": [{
                "background": "background.png",
                "icons": [{"object_id": "logo", "role": "brand_lockup", "file": "logo.png", "x": 0.8, "y": 0.05, "w": 0.1, "h": 0.1}],
            }],
        }), encoding="utf-8")
        deck = root / "deck.pptx"
        composed = run("scripts/compose_pptx.py", str(layout), str(deck))
        assert composed.returncode == 0, composed.stdout + composed.stderr
        manifest = root / "slide-object-manifest.json"
        built = run("scripts/build_object_manifest.py", str(layout), "--output", str(manifest))
        assert built.returncode == 0, built.stdout + built.stderr
        objects = json.loads(manifest.read_text(encoding="utf-8"))["slides"][0]["objects"]
        paths = {item["object_id"]: item.get("source_path") for item in objects}
        assert paths["background"] == "assets/background.png", paths
        assert paths["logo"] == "assets/logo.png", paths
        audited = run("scripts/semantic_object_audit.py", str(deck), "--object-manifest", str(manifest), "--require-source-hashes")
        assert audited.returncode == 0, audited.stdout + audited.stderr
    print("separate assets_dir object-manifest paths: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
